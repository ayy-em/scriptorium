"""CLI and programmatic interface for converting audio files between formats."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import run_ffmpeg
from scripts.formats._utils import (
    AUDIO_EXTS,
    QUALITY_PRESETS,
    VIDEO_EXTS,
    BatchConvertError,
    formats_inputs_dir,
    formats_outputs_dir,
    run_convert,
)

TITLE = "Convert audio"
DESCRIPTION = "Transcode audio files (or extract audio from video) to a different format."

_AUDIO_OUT_FORMATS = ["mp3", "wav", "aac", "flac", "ogg", "m4a", "opus"]
_LOSSLESS_EXTS = frozenset({".wav", ".flac"})
_SOURCE_EXTS = AUDIO_EXTS | VIDEO_EXTS


def _transcode(input_path: Path, output: Path, quality: str) -> None:
    """Build and run the ffmpeg transcode command for audio output.

    Args:
        input_path: Source file (audio or video).
        output: Destination audio file.
        quality: Quality preset key.
    """
    preset = QUALITY_PRESETS[quality]
    if output.suffix.lower() in _LOSSLESS_EXTS:
        args = ["-i", str(input_path), str(output)]
    else:
        args = ["-i", str(input_path), "-b:a", preset["audio_bitrate"], str(output)]
    run_ffmpeg(args)


def convert(
    source: Path,
    to_format: str,
    outputs_dir: Path,
    *,
    quality: str = "medium",
) -> list[Path]:
    """Transcode a single audio/video file or a directory of files to a target audio format.

    Args:
        source: Source file or directory of audio/video files.
        to_format: Target audio extension without leading dot (e.g. "mp3", "flac").
        outputs_dir: Directory where transcoded files are written.
        quality: One of "low", "medium", "high", "max". Defaults to "medium".

    Returns:
        List of successfully created output Paths.

    Raises:
        ValueError: If quality is not a recognised preset.
        subprocess.CalledProcessError: If ffmpeg fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality {quality!r}. Choose from: {', '.join(QUALITY_PRESETS)}")

    def _fn(inp: Path, out: Path) -> None:
        _transcode(inp, out, quality)

    return run_convert(source, _SOURCE_EXTS, outputs_dir, to_format, _fn)


_EXAMPLES = """
examples:
  uv run main.py formats.convert_audio podcast.mp4 --to mp3
  uv run main.py formats.convert_audio --to flac --quality max
  uv run main.py formats.convert_audio songs/ --to opus --quality high
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py formats.convert_audio",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Source file or directory (default: formats/inputs/)",
    )
    parser.add_argument(
        "--to",
        required=True,
        dest="to_format",
        metavar="FORMAT",
        choices=_AUDIO_OUT_FORMATS,
        help="Target format",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        choices=list(QUALITY_PRESETS),
        help="Quality preset (default: medium). Ignored for lossless targets (wav, flac).",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: formats/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to convert()."""
    args = get_parser().parse_args()
    source = args.source or formats_inputs_dir()
    out_dir = args.outputs or formats_outputs_dir()

    try:
        outputs = convert(source, args.to_format, out_dir, quality=args.quality)
        for o in outputs:
            print(o)
        sys.exit(0)
    except BatchConvertError as e:
        for o in e.succeeded:
            print(o)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
