"""CLI and programmatic interface for joining media files."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import random
import re
import sys
import tempfile

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from core.paths import move_to_past_inputs
from core.progress import ProgressReporter
from scripts.av._utils import (
    av_inputs_dir,
    find_media_files,
    probe_streams,
    run_ffmpeg,
    run_ffmpeg_stderr,
    run_ffprobe,
)
from scripts.formats._utils import QUALITY_PRESETS

TITLE = "Join multiple media files"
DESCRIPTION = (
    "Stitch all media files in inputs/ in the chosen order. "
    "Files that already share a video format are joined without re-encoding; "
    "mismatched files are re-encoded to a common format first. Trailing black "
    "frames are trimmed and audio is loudness-normalised to −23 LUFS."
)
ACCEPTS: set[str] = {"video", "audio"}

_LUFS_TARGET = -23
_TRUE_PEAK = -1
_LRA = 7

DEFAULT_QUALITY = "high"

# Chosen for playback compatibility rather than fidelity: yuv420p and stereo
# 48 kHz are what every player, browser and phone accepts without complaint.
_TARGET_PIX_FMT = "yuv420p"
_TARGET_SAMPLE_RATE = "48000"
_TARGET_CHANNELS = "2"
_X264_PRESET = "medium"

# Video codecs an MP4 container holds happily. Anything else copied verbatim
# goes into Matroska instead, which accepts every combination we might produce.
_MP4_VIDEO_CODECS = frozenset({"h264", "hevc", "mpeg4", "av1", "mpeg2video", "mjpeg"})


@dataclass(frozen=True)
class _JoinProfile:
    """The single format every file must share for the concat demuxer to work.

    The concat demuxer stitches streams without decoding them, so it needs
    every input to agree on codec, geometry and stream layout. This records
    what that agreement is and whether the inputs already meet it.

    Attributes:
        reencode_video: True when the inputs disagree on some video parameter
            and each one has to be re-encoded to the target below.
        width: Target frame width, or None when there is no video.
        height: Target frame height, or None when there is no video.
        frame_rate: Target frame rate as the raw ffprobe fraction (e.g.
            "30000/1001"), or None when there is no video.
        has_video: Whether the output carries a video stream.
        has_audio: Whether the output carries an audio stream. When True, files
            without audio of their own are given a silent one.
        quality: Key into QUALITY_PRESETS driving CRF and audio bitrate.
    """

    reencode_video: bool
    width: int | None
    height: int | None
    frame_rate: str | None
    has_video: bool
    has_audio: bool
    quality: str


def join(
    inputs_dir: Path,
    output: Path,
    order: str = "filename",
    quality: str = DEFAULT_QUALITY,
) -> Path:
    """Concatenate all media files in inputs_dir.

    Files are sorted by order, trailing black frames trimmed, and audio
    loudness-normalised to -23 LUFS before stitching. Files that disagree on
    any video parameter the concat demuxer cares about are re-encoded to a
    common format — the largest input resolution, letterboxed — instead of
    being rejected.

    Sources that live inside the shared inputs tree are archived to
    ``inputs/processed/`` afterwards; sources anywhere else on the disk are
    left where they are. This used to create a ``processed/`` directory next to
    whatever the user pointed at and move their files into it, which is not a
    thing a join is entitled to do to someone's media library.

    Args:
        inputs_dir: Directory containing source media files (non-recursive).
        output: Resolved output file path.
        order: Sort order — "filename" (a→z), "random", or "date" (mtime asc).
        quality: Re-encode quality preset key. Ignored when no re-encode is
            needed for video, but always applied to audio bitrate.

    Returns:
        Path to the joined output file.

    Raises:
        FileNotFoundError: If no media files are found in inputs_dir.
        ValueError: If only one media file is found, or quality is unknown.
        RuntimeError: If audio-only files are mixed with video files.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality {quality!r}. Choose from: {', '.join(QUALITY_PRESETS)}")

    files = find_media_files(inputs_dir)
    if not files:
        raise FileNotFoundError(f"No media files found in {inputs_dir}")
    if len(files) == 1:
        raise ValueError(f"Only one file found in {inputs_dir} — nothing to join")

    files = _sort_files(files, order)
    streams_by_file = {f: probe_streams(f) for f in files}
    profile = _resolve_profile(files, streams_by_file, quality)
    if profile.reencode_video:
        print(
            f"  inputs disagree on video format → re-encoding all to "
            f"{profile.width}x{profile.height} H.264 (quality: {quality})",
        )

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as _tmp:
        work_dir = Path(_tmp)

        # Files preprocessed is the only honest axis here. Per-file ffmpeg
        # progress would report against a different total for each file and
        # send the bar backwards every time one finished.
        reporter = ProgressReporter()
        preprocessed = []
        for i, f in enumerate(files):
            reporter.update(i / (len(files) + 1), f"preparing {f.name} ({i + 1} of {len(files)})")
            preprocessed.append(_preprocess_file(f, streams_by_file[f], work_dir, i, profile))

        concat_list = work_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as cf:
            for f in preprocessed:
                cf.write(f"file '{f.resolve()}'\n")

        reporter.update(len(files) / (len(files) + 1), "joining", force=True)
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output)])
        reporter.finish()

    for f in files:
        move_to_past_inputs("av", f)

    return output


def _sort_files(files: list[Path], order: str) -> list[Path]:
    """Return files reordered according to order.

    Args:
        files: List of input file paths.
        order: "filename" (case-insensitive a→z), "random", or "date"
               (modification time, oldest first).

    Returns:
        Reordered list (new list; originals unchanged).
    """
    if order == "random":
        result = list(files)
        random.shuffle(result)
        return result
    if order == "date":
        return sorted(files, key=lambda f: f.stat().st_mtime)
    return sorted(files, key=lambda f: f.name.lower())


def _first_stream(streams: list[dict], codec_type: str) -> dict | None:
    """Return the first stream of the given type, or None if there is none.

    Args:
        streams: Stream dicts as returned by probe_streams.
        codec_type: Either "video" or "audio".

    Returns:
        The matching stream dict, or None.
    """
    return next((s for s in streams if s.get("codec_type") == codec_type), None)


def _parse_frame_rate(value: str | None) -> float:
    """Return an ffprobe frame-rate fraction as a float.

    Args:
        value: A fraction like "30000/1001", a bare number, or None.

    Returns:
        The frame rate in frames per second, or 0.0 when it cannot be read.
        Zero is what ffprobe itself reports for a stream with no meaningful
        rate, so it is treated as "unknown" rather than as an error.
    """
    if not value:
        return 0.0
    numerator, _, denominator = value.partition("/")
    try:
        if denominator:
            divisor = float(denominator)
            return float(numerator) / divisor if divisor else 0.0
        return float(numerator)
    except ValueError:
        return 0.0


def _video_fingerprint(video: dict) -> tuple:
    """Return the video parameters the concat demuxer refuses to reconcile.

    Two files whose fingerprints match can be stitched with a stream copy; any
    difference means both have to be decoded and re-encoded.

    Args:
        video: A video stream dict from probe_streams.

    Returns:
        Tuple of codec, geometry, pixel format, sample aspect ratio and frame
        rate.
    """
    return (
        video.get("codec_name"),
        video.get("width"),
        video.get("height"),
        video.get("pix_fmt"),
        video.get("sample_aspect_ratio"),
        video.get("avg_frame_rate"),
    )


def _resolve_profile(
    files: list[Path],
    streams_by_file: dict[Path, list[dict]],
    quality: str,
) -> _JoinProfile:
    """Decide the common format the inputs will be joined in.

    When every file already shares a video fingerprint the profile asks for no
    re-encode, preserving the fast stream-copy path. Otherwise the target is
    the largest input resolution and the highest input frame rate, so no clip
    is cropped and none is slowed down.

    Args:
        files: Input files in join order.
        streams_by_file: Probed streams for each file.
        quality: Quality preset key for any re-encode.

    Returns:
        The resolved profile.

    Raises:
        RuntimeError: If audio-only files are mixed with video files, which is
            a conversion rather than a format mismatch.
    """
    videos = {f: _first_stream(streams_by_file[f], "video") for f in files}
    with_video = [f for f in files if videos[f]]
    without_video = [f for f in files if not videos[f]]

    if with_video and without_video:
        listed = "\n".join(f"  - {f.name}" for f in without_video)
        raise RuntimeError(
            "Cannot join — these inputs have no video stream while the others do:\n"
            f"{listed}\n\n"
            "Joining audio to video is a different operation from fixing a format "
            "mismatch. Either join the audio files on their own, or give them a "
            "video track first."
        )

    has_audio = any(_first_stream(streams_by_file[f], "audio") for f in files)

    if not with_video:
        return _JoinProfile(
            reencode_video=False,
            width=None,
            height=None,
            frame_rate=None,
            has_video=False,
            has_audio=has_audio,
            quality=quality,
        )

    fingerprints = {_video_fingerprint(videos[f]) for f in with_video}
    widest = max(with_video, key=lambda f: (videos[f].get("width") or 0) * (videos[f].get("height") or 0))
    fastest = max(with_video, key=lambda f: _parse_frame_rate(videos[f].get("avg_frame_rate")))

    return _JoinProfile(
        reencode_video=len(fingerprints) > 1,
        width=videos[widest].get("width"),
        height=videos[widest].get("height"),
        frame_rate=videos[fastest].get("avg_frame_rate"),
        has_video=True,
        has_audio=has_audio,
        quality=quality,
    )


def _video_filter(profile: _JoinProfile) -> str:
    """Return the filter chain scaling a frame into the profile's geometry.

    Aspect ratio is preserved and the leftover space filled with black bars,
    so a portrait clip in a landscape join is letterboxed rather than
    stretched or cropped.

    Args:
        profile: The resolved join profile. Must have width and height set.

    Returns:
        An ffmpeg -vf filter chain string.
    """
    return (
        f"scale={profile.width}:{profile.height}:force_original_aspect_ratio=decrease,"
        f"pad={profile.width}:{profile.height}:(ow-iw)/2:(oh-ih)/2,"
        "setsar=1"
    )


def _temp_suffix(video: dict | None, profile: _JoinProfile) -> str:
    """Return the container extension for a preprocessed intermediate file.

    Audio always leaves preprocessing as AAC, so a copied video stream has to
    go somewhere that holds both. MP4 does for the common codecs; Matroska
    does for everything else.

    Args:
        video: The file's video stream, or None for audio-only input.
        profile: The resolved join profile.

    Returns:
        A suffix including the leading dot.
    """
    if video is None:
        return ".m4a"
    if profile.reencode_video:
        return ".mp4"
    return ".mp4" if video.get("codec_name") in _MP4_VIDEO_CODECS else ".mkv"


def _detect_trailing_black(
    file: Path,
    streams: list[dict],
    threshold: float = 0.10,
    min_duration: float = 0.05,
) -> float | None:
    """Return the start time (s) of trailing black frames, or None.

    Runs ffmpeg's blackdetect filter and checks whether the last detected
    black section extends to the end of the video.

    Args:
        file: Input video file to inspect.
        streams: Probed streams for the file.
        threshold: Pixel brightness threshold for "black" (0.0–1.0).
        min_duration: Minimum black-section length in seconds to consider.

    Returns:
        Start time in seconds of the trailing black section, or None if the
        video ends cleanly.
    """
    video_stream = _first_stream(streams, "video")
    if video_stream is None:
        return None

    try:
        duration = float(video_stream.get("duration") or "0")
    except ValueError, TypeError:
        return None
    if duration <= 0:
        return None

    stderr = run_ffmpeg_stderr(
        [
            "-i",
            str(file),
            "-vf",
            f"blackdetect=d={min_duration}:pix_th={threshold}",
            "-an",
            "-f",
            "null",
            "-",
        ]
    )

    pattern = re.compile(r"black_start:([\d.]+).*?black_end:([\d.]+)")
    black_sections = []
    for line in stderr.splitlines():
        m = pattern.search(line)
        if m:
            black_sections.append((float(m.group(1)), float(m.group(2))))

    if not black_sections:
        return None

    last_start, last_end = black_sections[-1]
    if last_end >= duration - 0.5:
        return last_start

    return None


def _find_last_keyframe_before(file: Path, t: float) -> float | None:
    """Return the pts (seconds) of the last I-frame strictly before time t.

    Seeks to up to 30 s before t for efficiency on long files.

    Args:
        file: Input video file.
        t: Upper time bound in seconds (exclusive).

    Returns:
        Keyframe timestamp in seconds, or None if no keyframes found before t.
    """
    seek_to = max(0.0, t - 30.0)
    data = run_ffprobe(
        [
            "-ss",
            str(seek_to),
            "-select_streams",
            "v:0",
            "-skip_frame",
            "nokey",
            "-show_frames",
            "-show_entries",
            "frame=best_effort_timestamp_time",
            str(file),
        ]
    )
    pts_values = []
    for frame in data.get("frames", []):
        raw = frame.get("best_effort_timestamp_time")
        if raw in (None, "N/A", "NaN"):
            continue
        try:
            pts = float(raw)
        except ValueError, TypeError:
            continue
        if pts < t:
            pts_values.append(pts)
    return max(pts_values) if pts_values else None


def _resolve_trim_end(file: Path, streams: list[dict], profile: _JoinProfile) -> float | None:
    """Return the time to cut a file short at, or None to keep all of it.

    A stream copy can only cut on a keyframe, so a trim point is snapped back
    to the previous one and a little black is left in. A re-encode has no such
    constraint and cuts exactly where the black starts.

    Args:
        file: Source media file.
        streams: Probed streams for the file.
        profile: The resolved join profile.

    Returns:
        Trim point in seconds, or None.
    """
    black_start = _detect_trailing_black(file, streams)
    if black_start is None:
        return None

    if profile.reencode_video:
        print(f"  [{file.name}] trailing black at {black_start:.3f}s → trimmed")
        return black_start

    keyframe = _find_last_keyframe_before(file, black_start)
    if keyframe is None or keyframe <= 0:
        return None
    print(f"  [{file.name}] trailing black at {black_start:.3f}s → trim to keyframe {keyframe:.3f}s")
    return keyframe


def _preprocess_file(
    file: Path,
    streams: list[dict],
    work_dir: Path,
    idx: int,
    profile: _JoinProfile,
) -> Path:
    """Bring one file into the join profile, trimming trailing black as it goes.

    Returns a temp file in work_dir if any processing was applied, or the
    original path when the file already matches the profile and has neither
    black to trim nor audio to normalise.

    Temp files are named by index to guarantee uniqueness regardless of input
    filenames.

    Args:
        file: Source media file.
        streams: Probed streams for the file.
        work_dir: Directory for temporary output files.
        idx: Zero-based position in the input sequence (used for temp filename).
        profile: The resolved join profile.

    Returns:
        Path to processed file, or original path if no changes were needed.
    """
    video = _first_stream(streams, "video")
    audio = _first_stream(streams, "audio")

    trim_end = _resolve_trim_end(file, streams, profile) if video else None
    needs_silent_audio = profile.has_audio and audio is None

    if trim_end is None and audio is None and not needs_silent_audio and not profile.reencode_video:
        return file

    preset = QUALITY_PRESETS[profile.quality]
    temp_file = work_dir / f"{idx:03d}{_temp_suffix(video, profile)}"

    args: list[str] = ["-i", str(file)]
    if needs_silent_audio:
        args += [
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout=stereo:sample_rate={_TARGET_SAMPLE_RATE}",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
        ]
    if trim_end is not None:
        args += ["-to", str(trim_end)]

    if video and profile.reencode_video:
        args += [
            "-vf",
            _video_filter(profile),
            "-c:v",
            "libx264",
            "-preset",
            _X264_PRESET,
            "-crf",
            preset["crf"],
            "-pix_fmt",
            _TARGET_PIX_FMT,
        ]
        if profile.frame_rate:
            args += ["-r", profile.frame_rate]
    elif video:
        args += ["-c:v", "copy"]

    if audio or needs_silent_audio:
        # Silence has no loudness to normalise, and loudnorm on an empty signal
        # is an invitation for the filter to do something surprising.
        if audio:
            args += ["-af", f"loudnorm=I={_LUFS_TARGET}:TP={_TRUE_PEAK}:LRA={_LRA}"]
        args += [
            "-c:a",
            "aac",
            "-b:a",
            preset["audio_bitrate"],
            "-ar",
            _TARGET_SAMPLE_RATE,
            "-ac",
            _TARGET_CHANNELS,
        ]
    else:
        args += ["-an"]
    args.append(str(temp_file))

    run_ffmpeg(args)
    return temp_file


_EXAMPLES = """
examples:
  uv run main.py av.join
  uv run main.py av.join --order random
  uv run main.py av.join --inputs path/to/clips/ --output path/to/out.mp4
  uv run main.py av.join --order date --output joined.mp4
  uv run main.py av.join --quality max
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py av.join",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Input directory (default: av/inputs/)",
    )
    parser.add_argument(
        "--order",
        choices=["filename", "random", "date"],
        default="filename",
        help=(
            "Sequence of input files: filename (a→z), random, "
            "or date (modification time, oldest first). Default: filename."
        ),
    )
    parser.add_argument(
        "--quality",
        default=DEFAULT_QUALITY,
        choices=list(QUALITY_PRESETS),
        help=(
            "Quality preset for files that have to be re-encoded to a common "
            "format, and for the audio track in every case (default: high). "
            "max = CRF 0 (lossless H.264)."
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: timestamp-named in outputs/av/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to join()."""
    args = get_parser().parse_args()

    src_dir = args.inputs or av_inputs_dir()
    src_files = find_media_files(src_dir)
    ext = src_files[0].suffix if src_files else ".mp4"
    output = resolve_output(args.output, theme="av", ext=ext)

    try:
        output = join(src_dir, output, order=args.order, quality=args.quality)
        print(f"Joined -> {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
