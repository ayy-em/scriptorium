"""CLI and programmatic interface for joining media files."""

import argparse
from pathlib import Path
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
)

TITLE = "Join multiple media files"
DESCRIPTION = "Stitch all media files in inputs/ in sorted order and save to outputs/."
ACCEPTS: set[str] = {"video", "audio"}


def join(inputs_dir: Path, output: Path) -> Path:
    """Concatenate all media files in inputs_dir in lexicographic order.

    Checks that all files share the same video codec, audio codec, and
    resolution. Raises clearly if incompatibilities are found, prompting the
    user to convert files to a common format first.

    Args:
        inputs_dir: Directory containing source media files (non-recursive).
        output: Resolved output file path.

    Returns:
        Path to the joined output file.

    Raises:
        FileNotFoundError: If no media files are found in inputs_dir.
        ValueError: If only one media file is found.
        RuntimeError: If codec or resolution mismatches are detected.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    files = find_media_files(inputs_dir)
    if not files:
        raise FileNotFoundError(f"No media files found in {inputs_dir}")
    if len(files) == 1:
        raise ValueError(f"Only one file found in {inputs_dir} — nothing to join")

    _assert_compatible(files)

    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        concat_list = Path(tf.name)
        for f in files:
            tf.write(f"file '{f.resolve()}'\n")

    try:
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(output)])
    finally:
        concat_list.unlink(missing_ok=True)

    processed = inputs_dir / "processed"
    processed.mkdir(exist_ok=True)
    for f in files:
        shutil.move(str(f), processed / f.name)

    return output


def _assert_compatible(files: list[Path]) -> None:
    """Raise RuntimeError if files have mismatched codecs or resolutions.

    Args:
        files: List of media files to compare against the first file.

    Raises:
        RuntimeError: Describing each mismatch and how to resolve it.
    """

    def _first_stream(streams: list[dict], codec_type: str) -> dict | None:
        return next((s for s in streams if s.get("codec_type") == codec_type), None)

    ref_streams = probe_streams(files[0])
    ref_video = _first_stream(ref_streams, "video")
    ref_audio = _first_stream(ref_streams, "audio")
    issues: list[str] = []

    for f in files[1:]:
        streams = probe_streams(f)
        video = _first_stream(streams, "video")
        audio = _first_stream(streams, "audio")

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
        if ref_audio and audio:
            if ref_audio.get("codec_name") != audio.get("codec_name"):
                issues.append(
                    f"audio codec: {files[0].name} ({ref_audio.get('codec_name')})"
                    f" ≠ {f.name} ({audio.get('codec_name')})"
                )

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
  uv run main.py av.join --inputs path/to/clips/ --output path/to/out.mp4
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
        output = join(src_dir, output)
        print(f"Joined -> {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
