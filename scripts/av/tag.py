"""CLI and programmatic interface for reading and writing media metadata tags."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import tempfile

from scripts.av._utils import COVER_SUPPORTED_EXTS, av_inputs_dir, av_outputs_dir, read_tags, run_ffmpeg

TITLE = "Read/write media metadata tags"
DESCRIPTION = (
    "Read or write metadata fields (title, artist, album, date, comment) and album art."
    " With no write flags, prints current tags."
)


def get_tags(file: Path) -> dict[str, str]:
    """Read container-level metadata tags from a media file.

    Args:
        file: Media file to read.

    Returns:
        Dict mapping tag name to value.
    """
    return read_tags(file)


def write_tags(  # noqa: PLR0913
    input: Path,
    output: Path,
    *,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    date: str | None = None,
    comment: str | None = None,
    cover: Path | None = None,
    force: bool = False,
) -> None:
    """Write metadata tags (and optionally cover art) to a media file.

    Cover art embedding is only supported for mp4, m4v, m4a, mp3, mkv, and
    flac containers. For other formats, pass force=True to attempt anyway.

    Args:
        input: Source media file.
        output: Destination file path.
        title: Title tag value.
        artist: Artist tag value.
        album: Album tag value.
        date: Date/year tag value.
        comment: Comment tag value.
        cover: Path to a cover image to embed.
        force: If True, skip the format check for cover art embedding.

    Raises:
        ValueError: If no tags or cover are provided, or if cover embedding is
            attempted for an unsupported format without force=True.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    metadata: dict[str, str] = {}
    if title is not None:
        metadata["title"] = title
    if artist is not None:
        metadata["artist"] = artist
    if album is not None:
        metadata["album"] = album
    if date is not None:
        metadata["date"] = date
    if comment is not None:
        metadata["comment"] = comment

    if not metadata and cover is None:
        raise ValueError("No tags or cover provided — nothing to write")

    if cover is not None and not force:
        ext = input.suffix.lower()
        if ext not in COVER_SUPPORTED_EXTS:
            raise ValueError(
                f"Cover art embedding is not supported for {ext!r} files.\n"
                f"Supported formats: {', '.join(sorted(COVER_SUPPORTED_EXTS))}.\n"
                "Pass --force to attempt embedding anyway."
            )

    args = ["-i", str(input)]
    if cover is not None:
        args += ["-i", str(cover)]
        args += ["-map", "0", "-map", "1"]

    for key, value in metadata.items():
        args += ["-metadata", f"{key}={value}"]

    if cover is not None:
        args += ["-disposition:v:1", "attached_pic"]

    args += ["-codec", "copy"]
    args.append(str(output))

    run_ffmpeg(args)


_EXAMPLES = """
examples:
  uv run main.py av.tag video.mp4                                      # print current tags
  uv run main.py av.tag video.mp4 --title "My Title" --artist "Artist"
  uv run main.py av.tag audio.mp3 --cover cover.jpg --in-place
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.tag",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Source media file (bare name resolves to av/inputs/)")
    parser.add_argument("--title", help="Title tag")
    parser.add_argument("--artist", help="Artist tag")
    parser.add_argument("--album", help="Album tag")
    parser.add_argument("--date", help="Date/year tag")
    parser.add_argument("--comment", help="Comment tag")
    parser.add_argument("--cover", type=Path, metavar="IMAGE", help="Cover art image to embed")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force cover embedding even for unsupported container formats",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        dest="in_place",
        help="Overwrite source file instead of writing to outputs/",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: av/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to get_tags() or write_tags()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    has_write_flags = any([args.title, args.artist, args.album, args.date, args.comment, args.cover])

    if not has_write_flags:
        try:
            tags = get_tags(input_file)
            if not tags:
                print("(no tags found)")
            else:
                for key, value in sorted(tags.items()):
                    print(f"{key}: {value}")
            sys.exit(0)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)

    if args.in_place:
        fd, tmp_name = tempfile.mkstemp(suffix=input_file.suffix, dir=input_file.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            write_tags(
                input_file,
                tmp,
                title=args.title,
                artist=args.artist,
                album=args.album,
                date=args.date,
                comment=args.comment,
                cover=args.cover,
                force=args.force,
            )
            shutil.move(str(tmp), input_file)
            print(f"Updated: {input_file}")
            sys.exit(0)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            print(f"error: {e}", file=sys.stderr)
            sys.exit(1)

    outputs_dir = args.outputs or av_outputs_dir()
    output = outputs_dir / input_file.name
    try:
        write_tags(
            input_file,
            output,
            title=args.title,
            artist=args.artist,
            album=args.album,
            date=args.date,
            comment=args.comment,
            cover=args.cover,
            force=args.force,
        )
        print(f"Written: {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
