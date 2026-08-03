"""Shared ffmpeg/ffprobe utilities for the av script bundle."""

import json
from pathlib import Path
import subprocess
import sys
import threading

from core.paths import inputs_dir, outputs_dir
from core.progress import ProgressReporter

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

MEDIA_EXTS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".mov",
        ".avi",
        ".webm",
        ".flv",
        ".m4v",
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".ogg",
        ".m4a",
        ".wma",
        ".opus",
    }
)

AUDIO_ONLY_EXTS = frozenset(
    {
        ".mp3",
        ".wav",
        ".aac",
        ".flac",
        ".ogg",
        ".m4a",
        ".wma",
        ".opus",
    }
)

# Containers with reliable cover-art embedding support via ffmpeg.
COVER_SUPPORTED_EXTS = frozenset({".mp4", ".m4v", ".m4a", ".mp3", ".mkv", ".flac"})


# Colon-separated field counts a timestamp can have: HH:MM:SS and MM:SS.
# Anything else is treated as bare seconds.
_HMS_PARTS = 3
_MS_PARTS = 2


def parse_time(value: str) -> float:
    """Parse a timestamp string into seconds.

    Args:
        value: Time as HH:MM:SS, MM:SS, or bare seconds (int/float).

    Returns:
        Total seconds as a float.

    Raises:
        ValueError: If the format is unrecognised.
    """
    parts = value.split(":")
    try:
        if len(parts) == _HMS_PARTS:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == _MS_PARTS:
            return int(parts[0]) * 60 + float(parts[1])
        return float(parts[0])
    except ValueError, IndexError:
        raise ValueError(f"Cannot parse timestamp: {value!r}")


def format_time(seconds: float) -> str:
    """Format seconds into HH:MM:SS.mmm for ffmpeg.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted string like '01:23:04.500'.
    """
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def av_inputs_dir() -> Path:
    """Return the default av inputs directory, creating it if needed."""
    return inputs_dir("av")


def av_outputs_dir() -> Path:
    """Return the default av outputs directory, creating it if needed."""
    return outputs_dir("av")


def find_media_files(directory: Path) -> list[Path]:
    """Return a sorted list of media files in a directory (non-recursive).

    Args:
        directory: Directory to scan.

    Returns:
        Sorted list of Paths whose suffix is in MEDIA_EXTS.
    """
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in MEDIA_EXTS)


def run_ffmpeg(args: list[str]) -> None:
    """Run an ffmpeg command, suppressing the startup banner.

    Args:
        args: Arguments passed after the ffmpeg binary name.

    Raises:
        subprocess.CalledProcessError: If ffmpeg exits non-zero.
        FileNotFoundError: If ffmpeg is not on PATH.
    """
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-y", *args],
        check=True,
        capture_output=True,
        creationflags=_CREATION_FLAGS,
    )


def format_clock(seconds: float) -> str:
    """Format seconds as a compact clock for a progress label.

    Unlike ``format_time``, which feeds ffmpeg and needs milliseconds, this is
    read by a person watching a bar move and drops everything below a second.

    Args:
        seconds: Time in seconds.

    Returns:
        ``M:SS`` under an hour, ``H:MM:SS`` at or above one.
    """
    total = int(seconds)
    h, m, s = total // 3600, (total % 3600) // 60, total % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _position_from_progress(key: str, value: str) -> float | None:
    """Read a media position in seconds out of one ffmpeg -progress field.

    Args:
        key: Field name from ffmpeg's progress stream.
        value: Field value.

    Returns:
        Position in seconds, or None if this field does not carry one.
    """
    # out_time_ms is misnamed in ffmpeg — it is microseconds, same as
    # out_time_us — so it is read with the same divisor rather than trusted.
    if key in ("out_time_us", "out_time_ms"):
        try:
            return int(value) / 1_000_000
        except ValueError:
            return None
    if key == "out_time":
        try:
            return parse_time(value)
        except ValueError:
            return None
    return None


def run_ffmpeg_with_progress(
    args: list[str],
    *,
    total_seconds: float | None = None,
    label_prefix: str = "",
) -> None:
    """Run an ffmpeg command, reporting progress as it goes.

    Same contract as ``run_ffmpeg`` — banner suppressed, overwrite enabled,
    raises on non-zero exit — but ffmpeg is asked for its machine-readable
    progress stream and each report is forwarded via ``core.progress``.

    Args:
        args: Arguments passed after the ffmpeg binary name.
        total_seconds: Expected duration of the *output*, which is what ffmpeg
            reports against. None when it is not knowable, in which case
            progress is reported without a fraction and the UI's bar stays
            indeterminate.
        label_prefix: Prepended to each progress label, to name the stage when a
            script makes several passes.

    Raises:
        subprocess.CalledProcessError: If ffmpeg exits non-zero.
        FileNotFoundError: If ffmpeg is not on PATH.
    """
    cmd = ["ffmpeg", "-hide_banner", "-y", "-progress", "pipe:1", "-nostats", *args]
    reporter = ProgressReporter(label_prefix=label_prefix)
    total = total_seconds if total_seconds and total_seconds > 0 else None

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=_CREATION_FLAGS,
    )

    # ffmpeg is chatty on stderr and the pipe is finite, so it has to be drained
    # concurrently — reading stdout to exhaustion first would deadlock on any
    # file verbose enough to fill the stderr buffer.
    captured_stderr: list[bytes] = []
    drain = threading.Thread(target=lambda: captured_stderr.append(proc.stderr.read()), daemon=True)
    drain.start()

    for raw in proc.stdout:
        key, _, value = raw.decode(errors="replace").strip().partition("=")
        position = _position_from_progress(key, value)
        if position is None:
            continue
        label = f"{format_clock(position)} / {format_clock(total)}" if total else format_clock(position)
        reporter.update(None if total is None else position / total, label)

    proc.stdout.close()
    drain.join()
    returncode = proc.wait()
    stderr = captured_stderr[0] if captured_stderr else b""

    if returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=b"", stderr=stderr)
    reporter.finish()


def run_ffmpeg_stderr(args: list[str]) -> str:
    """Run ffmpeg and return its stderr output as a string.

    Unlike run_ffmpeg, does not raise on non-zero exit — used for filter
    probes (e.g. blackdetect with -f null) where the filter log in stderr is
    more useful than the exit code.

    Args:
        args: Arguments passed after the ffmpeg binary name.

    Returns:
        stderr decoded as UTF-8 (with replacement for invalid bytes).
    """
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", *args],
        check=False,
        capture_output=True,
        creationflags=_CREATION_FLAGS,
    )
    return result.stderr.decode("utf-8", errors="replace")


def run_ffprobe(args: list[str]) -> dict:
    """Run ffprobe in JSON mode and return the parsed output.

    Args:
        args: Arguments passed after the ffprobe binary name.

    Returns:
        Parsed JSON dict from ffprobe stdout.

    Raises:
        subprocess.CalledProcessError: If ffprobe exits non-zero.
        FileNotFoundError: If ffprobe is not on PATH.
    """
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", *args],
        check=True,
        capture_output=True,
        text=True,
        creationflags=_CREATION_FLAGS,
    )
    return json.loads(result.stdout)


def probe_streams(file: Path) -> list[dict]:
    """Return stream metadata for a media file.

    Args:
        file: Media file to probe.

    Returns:
        List of stream dicts (codec_type, codec_name, width, height, duration, …).
    """
    data = run_ffprobe(["-show_streams", str(file)])
    return data.get("streams", [])


def probe_duration(file: Path) -> float:
    """Return a media file's duration in seconds.

    Prefers the container's own duration and falls back to the longest stream,
    since a stream-copied or badly muxed file can carry one without the other.

    Args:
        file: Media file to probe.

    Returns:
        Duration in seconds.

    Raises:
        ValueError: If neither the container nor any stream reports a duration.
    """
    data = run_ffprobe(["-show_format", "-show_streams", str(file)])
    container = data.get("format", {}).get("duration")
    if container is not None:
        try:
            return float(container)
        except ValueError:
            pass

    stream_durations = []
    for stream in data.get("streams", []):
        try:
            stream_durations.append(float(stream["duration"]))
        except KeyError, TypeError, ValueError:
            continue
    if stream_durations:
        return max(stream_durations)
    raise ValueError(f"Cannot determine duration of {file}")


def probe_duration_or_none(file: Path) -> float | None:
    """Return a media file's duration, or None if it cannot be determined.

    For progress reporting, where an unknown duration costs a determinate bar
    and nothing else. Failing a transcode because ffprobe would not commit to a
    duration would be a worse trade.

    Args:
        file: Media file to probe.

    Returns:
        Duration in seconds, or None.
    """
    try:
        return probe_duration(file)
    except Exception:
        return None


def read_tags(file: Path) -> dict[str, str]:
    """Read container-level metadata tags from a media file.

    Args:
        file: Media file to read.

    Returns:
        Dict mapping tag name to value (e.g. {"title": "…", "artist": "…"}).
    """
    data = run_ffprobe(["-show_format", str(file)])
    return data.get("format", {}).get("tags", {})
