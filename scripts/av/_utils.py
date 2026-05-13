"""Shared ffmpeg/ffprobe utilities for the av script bundle."""

import json
from pathlib import Path
import subprocess

from core.paths import inputs_dir, outputs_dir

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
    subprocess.run(["ffmpeg", "-hide_banner", "-y", *args], check=True)


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


def read_tags(file: Path) -> dict[str, str]:
    """Read container-level metadata tags from a media file.

    Args:
        file: Media file to read.

    Returns:
        Dict mapping tag name to value (e.g. {"title": "…", "artist": "…"}).
    """
    data = run_ffprobe(["-show_format", str(file)])
    return data.get("format", {}).get("tags", {})
