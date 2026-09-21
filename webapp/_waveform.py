"""Peak extraction for the ``av.trim`` waveform editor.

The waveform used to be decoded in the browser, with ``decodeAudioData`` over
the raw file. That made the editor's usefulness a property of the browser
rather than of the file: MP3 needs a build with proprietary codecs, which not
every Chromium is, and MKV, AVI, FLV and WMA are never decodable that way. A
file the trimmer could happily cut would show "Waveform unavailable" and send
the user back to typing timestamps blind.

ffmpeg is already a hard requirement for every ``av.*`` script, so the machine
running the editor can always decode what the editor is about to cut. Reading
the peaks here rather than in the page makes the waveform available for
exactly the set of files the script accepts, and keeps a two-hour recording
from being decoded into browser memory in full.
"""

import array
from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
import sys

from scripts.av._utils import probe_duration_or_none

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Full-scale value of the signed 16-bit samples ffmpeg is asked for.
_S16_FULL_SCALE = 32768.0

# Samples wanted per drawn bucket. More than enough for a peak to survive
# bucketing, few enough that the rate stays low on a long file.
_SAMPLES_PER_BUCKET = 20

# Bounds on the decode rate. The ceiling caps the work on a short file, where
# the formula would otherwise ask for far more resolution than 900 bars can
# show. The floor keeps the resampler's low-pass from flattening a long file
# into a silent-looking line.
_MIN_RATE = 1000
_MAX_RATE = 8000

# Guards against a caller asking for a canvas-sized array or a single bar.
_MIN_BUCKETS = 16
_MAX_BUCKETS = 4000

# Duration assumed when ffprobe will not commit to one, only to pick a decode
# rate. The peaks themselves come from however much audio ffmpeg actually
# emits, so a wrong guess costs resolution, never correctness.
_FALLBACK_DURATION = 600.0


class WaveformError(RuntimeError):
    """Raised when peaks cannot be read from a file."""


class StagedInputError(ValueError):
    """Raised when a client-supplied path is not one the server will read.

    Attributes:
        status: The HTTP status the endpoint should answer with.
    """

    def __init__(self, message: str, status: int) -> None:
        """Initialise with the reason and the status it maps to."""
        super().__init__(message)
        self.status = status


def resolve_staged_input(raw: str, root: Path) -> Path:
    """Resolve a client-supplied path to a file the server staged for a run.

    The waveform endpoint reads whatever it is pointed at and hands the result
    back, so "which paths may it read" is the whole of its security. Staged
    inputs are the answer: every path the trim page can hold came from the
    upload endpoint or a drop session, both of which live under the shared
    inputs root. Anything else on the disk is refused, which keeps a page that
    can reach localhost from reading arbitrary files through this.

    Resolution happens before the containment check so that ``..`` segments and
    symlinks are collapsed first — checking the unresolved path would accept
    ``inputs/../../.ssh/id_rsa``.

    Args:
        raw: Path as the client sent it.
        root: The inputs directory paths must be contained by.

    Returns:
        The resolved path.

    Raises:
        StagedInputError: For an empty, unusable, out-of-tree or absent path.
    """
    if not raw:
        raise StagedInputError("No path given", 400)
    try:
        target = Path(raw).expanduser().resolve()
        root = root.resolve()
    except OSError:
        raise StagedInputError("Unusable path", 400)
    if not target.is_relative_to(root):
        raise StagedInputError("Path is outside the inputs directory", 403)
    if not target.is_file():
        raise StagedInputError("No such file", 404)
    return target


@dataclass(frozen=True)
class Waveform:
    """Normalised peak envelope of one file's audio.

    Attributes:
        duration: Length of the audio in seconds.
        peaks: One value per bucket, each in ``[0.0, 1.0]``, scaled so the
            loudest bucket is 1.0. Empty when the file carries no audio.
    """

    duration: float
    peaks: list[float]

    def as_dict(self) -> dict:
        """Return the JSON-serialisable form the page consumes."""
        return {"duration": self.duration, "peaks": self.peaks}


def _decode_rate(duration: float, buckets: int) -> int:
    """Pick the sample rate to decode at for *duration* seconds and *buckets* bars.

    Args:
        duration: Audio length in seconds.
        buckets: Number of bars the page will draw.

    Returns:
        A sample rate in Hz, within the module's floor and ceiling.
    """
    if duration <= 0:
        return _MAX_RATE
    wanted = math.ceil(buckets * _SAMPLES_PER_BUCKET / duration)
    return max(_MIN_RATE, min(_MAX_RATE, wanted))


def _decode_mono_pcm(file: Path, rate: int) -> array.array:
    """Decode a file's audio to mono signed-16-bit PCM at *rate*.

    Args:
        file: Media file to read.
        rate: Sample rate in Hz.

    Returns:
        The decoded samples.

    Raises:
        WaveformError: If ffmpeg is missing or fails to decode the file.
    """
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-v",
        "error",
        "-i",
        str(file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(rate),
        "-f",
        "s16le",
        "-",
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, creationflags=_CREATION_FLAGS)
    except FileNotFoundError:
        raise WaveformError("ffmpeg is not on PATH")

    if result.returncode != 0 and not result.stdout:
        detail = result.stderr.decode("utf-8", errors="replace").strip().splitlines()
        raise WaveformError(detail[-1] if detail else "ffmpeg could not decode this file")

    samples = array.array("h")
    payload = result.stdout
    # A truncated trailing sample would make frombytes reject the whole buffer,
    # which is a poor trade for the half-sample it protects.
    samples.frombytes(payload[: len(payload) - (len(payload) % samples.itemsize)])
    if sys.byteorder != "little":
        samples.byteswap()
    return samples


def _bucket_peaks(samples: array.array, buckets: int) -> list[float]:
    """Reduce raw samples to one normalised peak per bucket.

    Peaks rather than averages: an average over thousands of samples of a
    waveform centred on zero tends to zero regardless of how loud the audio is,
    which draws a flat line for every file.

    Args:
        samples: Signed 16-bit mono samples.
        buckets: Number of buckets to produce.

    Returns:
        One value per bucket in ``[0.0, 1.0]``, or an empty list for no samples.
    """
    total = len(samples)
    if total == 0:
        return []

    peaks: list[float] = []
    for i in range(buckets):
        lo = total * i // buckets
        hi = max(total * (i + 1) // buckets, lo + 1)
        window = samples[lo:hi]
        # min() and max() run in C over the array; an abs() per sample in
        # Python would dominate the cost of the whole endpoint.
        highest = max(window)
        lowest = min(window)
        extreme = highest if highest >= -lowest else -lowest
        # -32768 has no positive counterpart in int16, so the clamp is real.
        peaks.append(min(extreme / _S16_FULL_SCALE, 1.0))

    loudest = max(peaks)
    if loudest > 0:
        peaks = [p / loudest for p in peaks]
    return peaks


def read_waveform(file: Path, buckets: int = 900) -> Waveform:
    """Read a normalised peak envelope for a media file's audio.

    Args:
        file: Media file to read. Any container ffmpeg can demux works,
            including video files, whose audio track is used.
        buckets: Number of peaks to return, clamped to a sane range.

    Returns:
        The file's duration and its peak envelope. ``peaks`` is empty for a
        file with no audio stream, which the page renders as "no waveform"
        rather than as an error.

    Raises:
        WaveformError: If the file cannot be decoded at all.
    """
    buckets = max(_MIN_BUCKETS, min(_MAX_BUCKETS, buckets))
    probed = probe_duration_or_none(file)
    rate = _decode_rate(probed if probed is not None else _FALLBACK_DURATION, buckets)
    samples = _decode_mono_pcm(file, rate)

    # The decoded stream is the authority on how much audio there is: a
    # container can carry a duration that its audio track does not fill.
    decoded_duration = len(samples) / rate if samples else 0.0
    duration = probed if probed is not None and probed > 0 else decoded_duration

    return Waveform(duration=duration, peaks=_bucket_peaks(samples, buckets))
