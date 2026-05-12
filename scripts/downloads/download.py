"""CLI and programmatic interface for downloading media from URLs via yt-dlp."""

import argparse
from pathlib import Path
import sys

import yt_dlp

TITLE = "Download media"
DESCRIPTION = "Download video (or extract audio as MP3) from a URL using yt-dlp."

_DOWNLOADS_DIR = Path(__file__).parent


def _outputs_dir() -> Path:
    """Return the default downloads outputs directory, creating it if needed.

    Returns:
        Path to scripts/downloads/outputs/.
    """
    d = _DOWNLOADS_DIR / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(
    url: str,
    outputs_dir: Path,
    *,
    filename: str | None = None,
    audio_only: bool = False,
) -> Path:
    """Download a video (or extract audio) from a URL using yt-dlp.

    Fetches the best available MP4 by default. When audio_only is True, extracts
    audio and converts it to MP3 via FFmpeg. FFmpeg must be on PATH for stream
    merging and audio conversion.

    Args:
        url: Source URL supported by yt-dlp (YouTube, Vimeo, etc.).
        outputs_dir: Directory where the output file is written.
        filename: Output file stem (no extension). Defaults to the video title.
        audio_only: When True, extract audio as MP3 instead of downloading video.

    Returns:
        Path to the downloaded output file.

    Raises:
        yt_dlp.utils.DownloadError: If yt-dlp fails to fetch or process the URL.
    """
    outputs_dir.mkdir(parents=True, exist_ok=True)

    stem = filename if filename else "%(title)s"

    if audio_only:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": str(outputs_dir / f"{stem}.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                }
            ],
        }
        output_ext = ".mp3"
    else:
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(outputs_dir / f"{stem}.%(ext)s"),
            "merge_output_format": "mp4",
        }
        output_ext = ".mp4"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        prepared = Path(ydl.prepare_filename(info))
        return prepared.with_suffix(output_ext)


_EXAMPLES = """
examples:
  uv run main.py downloads.download <url>
  uv run main.py downloads.download <url> --filename my_video
  uv run main.py downloads.download <url> --audio
  uv run main.py downloads.download <url> --audio --filename soundtrack
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py downloads.download",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="URL of the media to download")
    parser.add_argument(
        "--filename",
        default=None,
        metavar="NAME",
        help="Output file stem without extension (defaults to video title)",
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help="Extract audio as MP3 instead of downloading video",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: downloads/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to download()."""
    args = get_parser().parse_args()

    out_dir = args.outputs or _outputs_dir()

    try:
        output = download(args.url, out_dir, filename=args.filename, audio_only=args.audio)
        print(output)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
