"""CLI and programmatic interface for joining media files."""

import argparse
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from scripts.av._utils import (
    av_inputs_dir,
    find_media_files,
    probe_streams,
    run_ffmpeg,
    run_ffmpeg_stderr,
    run_ffprobe,
)

TITLE = "Join multiple media files"
DESCRIPTION = (
    "Stitch all media files in inputs/ in the chosen order. "
    "Trailing black frames are trimmed to the nearest keyframe and audio is "
    "loudness-normalised to −23 LUFS before joining."
)
ACCEPTS: set[str] = {"video", "audio"}

_LUFS_TARGET = -23
_TRUE_PEAK = -1
_LRA = 7


def join(inputs_dir: Path, output: Path, order: str = "filename") -> Path:
    """Concatenate all media files in inputs_dir.

    Files are sorted by order, trailing black frames trimmed to the nearest
    keyframe, and audio loudness-normalised to -23 LUFS before stitching.

    Args:
        inputs_dir: Directory containing source media files (non-recursive).
        output: Resolved output file path.
        order: Sort order — "filename" (a→z), "random", or "date" (mtime asc).

    Returns:
        Path to the joined output file.

    Raises:
        FileNotFoundError: If no media files are found in inputs_dir.
        ValueError: If only one media file is found.
        RuntimeError: If video codec or resolution mismatches are detected.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    files = find_media_files(inputs_dir)
    if not files:
        raise FileNotFoundError(f"No media files found in {inputs_dir}")
    if len(files) == 1:
        raise ValueError(f"Only one file found in {inputs_dir} — nothing to join")

    files = _sort_files(files, order)
    _assert_compatible(files)

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as _tmp:
        work_dir = Path(_tmp)

        preprocessed = [_preprocess_file(f, work_dir, i) for i, f in enumerate(files)]

        concat_list = work_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as cf:
            for f in preprocessed:
                cf.write(f"file '{f.resolve()}'\n")

        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output)])

    processed_dir = inputs_dir / "processed"
    processed_dir.mkdir(exist_ok=True)
    for f in files:
        shutil.move(str(f), processed_dir / f.name)

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


def _detect_trailing_black(
    file: Path,
    threshold: float = 0.10,
    min_duration: float = 0.05,
) -> float | None:
    """Return the start time (s) of trailing black frames, or None.

    Runs ffmpeg's blackdetect filter and checks whether the last detected
    black section extends to the end of the video.

    Args:
        file: Input video file to inspect.
        threshold: Pixel brightness threshold for "black" (0.0–1.0).
        min_duration: Minimum black-section length in seconds to consider.

    Returns:
        Start time in seconds of the trailing black section, or None if the
        video ends cleanly.
    """
    streams = probe_streams(file)
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
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


def _preprocess_file(file: Path, work_dir: Path, idx: int) -> Path:
    """Trim trailing black frames and loudness-normalise audio in one pass.

    Returns a temp file in work_dir if any processing was applied, or the
    original path when the file has neither a video stream (no black to trim)
    nor an audio stream (nothing to normalise).

    Temp files are named by index to guarantee uniqueness regardless of input
    filenames.

    Args:
        file: Source media file.
        work_dir: Directory for temporary output files.
        idx: Zero-based position in the input sequence (used for temp filename).

    Returns:
        Path to processed file, or original path if no changes were needed.
    """
    streams = probe_streams(file)
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    trim_end: float | None = None
    if has_video:
        black_start = _detect_trailing_black(file)
        if black_start is not None:
            kf = _find_last_keyframe_before(file, black_start)
            if kf is not None and kf > 0:
                trim_end = kf
                print(
                    f"  [{file.name}] trailing black at {black_start:.3f}s → trim to keyframe {trim_end:.3f}s",
                )

    needs_trim = trim_end is not None
    needs_normalize = has_audio

    if not needs_trim and not needs_normalize:
        return file

    out_ext = ".mp4" if has_video else ".m4a"
    temp_file = work_dir / f"{idx:03d}{out_ext}"

    args: list[str] = ["-i", str(file)]
    if needs_trim:
        args += ["-to", str(trim_end)]
    if has_video:
        args += ["-c:v", "copy"]
    if has_audio:
        args += [
            "-af",
            f"loudnorm=I={_LUFS_TARGET}:TP={_TRUE_PEAK}:LRA={_LRA}",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
        ]
    else:
        args += ["-an"]
    args.append(str(temp_file))

    run_ffmpeg(args)
    return temp_file


def _assert_compatible(files: list[Path]) -> None:
    """Raise RuntimeError if files have mismatched video codecs or resolutions.

    Audio codec mismatches are intentionally not checked: all audio is
    re-encoded to AAC during preprocessing, which resolves any mismatch.

    Args:
        files: List of media files to compare against the first file.

    Raises:
        RuntimeError: Describing each mismatch and how to resolve it.
    """

    def _first_stream(streams: list[dict], codec_type: str) -> dict | None:
        return next((s for s in streams if s.get("codec_type") == codec_type), None)

    ref_streams = probe_streams(files[0])
    ref_video = _first_stream(ref_streams, "video")
    issues: list[str] = []

    for f in files[1:]:
        streams = probe_streams(f)
        video = _first_stream(streams, "video")

        if ref_video and video:
            if ref_video.get("codec_name") != video.get("codec_name"):
                issues.append(
                    f"video codec: {files[0].name} ({ref_video.get('codec_name')})"
                    f" ≠ {f.name} ({video.get('codec_name')})"
                )
            ref_res = (ref_video.get("width"), ref_video.get("height"))
            res = (video.get("width"), video.get("height"))
            if ref_res != res:
                issues.append(f"resolution: {files[0].name} ({ref_res[0]}x{ref_res[1]}) ≠ {f.name} ({res[0]}x{res[1]})")

    if issues:
        bullet_list = "\n".join(f"  - {i}" for i in issues)
        raise RuntimeError(
            f"Cannot join — incompatible files detected:\n{bullet_list}\n\n"
            "Re-encode all files to a common format and resolution first, then retry:\n"
            "  uv run main.py formats.convert_video <file_or_dir> --to <format> --quality medium"
        )


_EXAMPLES = """
examples:
  uv run main.py av.join
  uv run main.py av.join --order random
  uv run main.py av.join --inputs path/to/clips/ --output path/to/out.mp4
  uv run main.py av.join --order date --output joined.mp4
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
        output = join(src_dir, output, order=args.order)
        print(f"Joined -> {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
