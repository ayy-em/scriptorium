"""CLI and programmatic interface for converting media files between formats."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import AUDIO_ONLY_EXTS, av_outputs_dir, find_media_files, run_ffmpeg

TITLE = "Convert media file"
DESCRIPTION = "Transcode a file (or directory of files) to a target container/codec."

# Maps quality name to ffmpeg CRF (video) and audio bitrate.
# max: CRF 0 is lossless for H.264/H.265; for audio-only targets bitrate is maximised.
QUALITY_PRESETS: dict[str, dict[str, str]] = {
    "low": {"crf": "28", "audio_bitrate": "96k"},
    "medium": {"crf": "23", "audio_bitrate": "128k"},
    "high": {"crf": "18", "audio_bitrate": "192k"},
    "max": {"crf": "0", "audio_bitrate": "320k"},
}


class BatchConvertError(RuntimeError):
    """Raised when one or more files fail in a batch convert run.

    Carries the list of successfully created outputs so callers can
    inspect partial results.
    """

    def __init__(self, message: str, succeeded: list[Path]) -> None:
        """Initialize with failure summary and list of paths that did succeed."""
        super().__init__(message)
        self.succeeded = succeeded


def convert(
    source: Path,
    to_format: str,
    outputs_dir: Path,
    *,
    quality: str = "medium",
) -> list[Path]:
    """Transcode a single file or a directory of files to a target format.

    Single-file mode raises on error. Batch mode (directory) continues on
    per-file errors and raises BatchConvertError at the end, which carries
    the list of files that did succeed.

    Args:
        source: Source media file or directory of media files.
        to_format: Target container extension without leading dot (e.g. "mp4", "mp3").
        outputs_dir: Directory where transcoded files are written.
        quality: One of "low", "medium", "high", "max". Defaults to "medium".
            max uses CRF 0 (lossless H.264) for video; 320 kbps for audio.
            Lossless audio formats (wav, flac) ignore the audio bitrate setting.

    Returns:
        List of successfully created output Paths.

    Raises:
        ValueError: If quality is not a recognised preset.
        subprocess.CalledProcessError: If ffmpeg fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """
    if quality not in QUALITY_PRESETS:
        raise ValueError(f"Unknown quality {quality!r}. Choose from: {', '.join(QUALITY_PRESETS)}")

    outputs_dir.mkdir(parents=True, exist_ok=True)
    ext = f".{to_format.lstrip('.')}"

    if source.is_dir():
        return _convert_batch(source, ext, outputs_dir, quality)

    output = outputs_dir / f"{source.stem}{ext}"
    _transcode(source, output, ext, quality)
    return [output]


def _transcode(input: Path, output: Path, ext: str, quality: str) -> None:
    """Build and run the ffmpeg transcode command for a single file.

    Args:
        input: Source file.
        output: Destination file.
        ext: Target extension (with dot).
        quality: Quality preset key.
    """
    preset = QUALITY_PRESETS[quality]
    is_audio_only = ext.lower() in AUDIO_ONLY_EXTS
    is_lossless_audio = ext.lower() in {".wav", ".flac"}

    if is_audio_only:
        if is_lossless_audio:
            # Lossless containers — let ffmpeg pick the codec; no bitrate control.
            args = ["-i", str(input), str(output)]
        else:
            args = ["-i", str(input), "-b:a", preset["audio_bitrate"], str(output)]
    else:
        args = [
            "-i",
            str(input),
            "-crf",
            preset["crf"],
            "-b:a",
            preset["audio_bitrate"],
            str(output),
        ]

    run_ffmpeg(args)


def _convert_batch(directory: Path, ext: str, outputs_dir: Path, quality: str) -> list[Path]:
    """Convert all media files in a directory, collecting per-file errors.

    Args:
        directory: Source directory (non-recursive).
        ext: Target extension (with dot).
        outputs_dir: Where outputs are written.
        quality: Quality preset key.

    Returns:
        List of successfully created Paths.

    Raises:
        BatchConvertError: If any files fail, after all files have been attempted.
    """
    files = find_media_files(directory)
    successes: list[Path] = []
    failures: list[str] = []

    for f in files:
        output = outputs_dir / f"{f.stem}{ext}"
        try:
            _transcode(f, output, ext, quality)
            successes.append(output)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise BatchConvertError(
            f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}",
            successes,
        )

    return successes


_EXAMPLES = """
examples:
  uv run main.py av.convert video.avi --to mp4
  uv run main.py av.convert clips/ --to mp4 --quality high
  uv run main.py av.convert podcast.mp4 --to mp3 --quality medium
"""


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to convert()."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.convert",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="Source file or directory")
    parser.add_argument(
        "--to",
        required=True,
        dest="to_format",
        metavar="FORMAT",
        help="Target format (e.g. mp4, mp3, wav, mov)",
    )
    parser.add_argument(
        "--quality",
        default="medium",
        choices=list(QUALITY_PRESETS),
        help=("Quality preset (default: medium). max = CRF 0 (lossless H.264) for video, 320 kbps for audio."),
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: av/outputs/)",
    )
    args = parser.parse_args()

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        outputs = convert(args.source, args.to_format, outputs_dir, quality=args.quality)
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
