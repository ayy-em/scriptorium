"""CLI and programmatic interface for converting a video segment to animated GIF or WebP."""

import argparse
from pathlib import Path
import sys
import tempfile

from scripts.av._utils import av_outputs_dir, run_ffmpeg

TITLE = "Video to animated GIF/WebP"
DESCRIPTION = "Convert a video segment to an animated GIF or WebP given start/end timestamps."

FORMATS = ("gif", "webp")


def to_anim(
    source: Path,
    start: str,
    end: str,
    outputs_dir: Path,
    *,
    fmt: str = "gif",
    fps: int = 15,
    width: int | None = None,
    speed: float = 1.0,
    loop: int = 0,
    filename: str | None = None,
) -> Path:
    """Convert a video segment to an animated GIF or WebP.

    GIF output uses a two-pass palette approach (palettegen then paletteuse) for
    significantly better colour quality than a single-pass encode. WebP is a
    single-pass encode with libwebp. Both formats require FFmpeg on PATH.

    Timestamps are passed directly to ffmpeg and accept any format it understands:
    HH:MM:SS, HH:MM:SS.ms, or bare seconds (e.g. "5", "1:30", "00:01:30.500").

    Speed is applied via a setpts filter (setpts=(1/speed)*PTS) before the fps
    filter, so --speed 2.0 plays back at 2x and --speed 0.5 plays at half speed.

    Args:
        source: Source video file.
        start: Start timestamp of the segment to extract.
        end: End timestamp of the segment to extract.
        outputs_dir: Directory where the output file is written.
        fmt: Output format — "gif" or "webp". Defaults to "gif".
        fps: Frame rate of the output animation. Defaults to 15.
        width: Output width in pixels; height is auto-scaled. Defaults to original width.
        speed: Playback speed multiplier. 2.0 = twice as fast, 0.5 = half speed. Defaults to 1.0.
        loop: Number of times to loop. 0 = infinite. Defaults to 0.
        filename: Output file stem (no extension). Defaults to the source file stem.

    Returns:
        Path to the created output file.

    Raises:
        ValueError: If fmt is not a recognised format, or speed is <= 0.
        subprocess.CalledProcessError: If ffmpeg fails.
        FileNotFoundError: If ffmpeg is not on PATH.
    """
    if fmt not in FORMATS:
        raise ValueError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")
    if speed <= 0:
        raise ValueError(f"speed must be > 0, got {speed}")

    outputs_dir.mkdir(parents=True, exist_ok=True)

    stem = filename or source.stem
    output = outputs_dir / f"{stem}.{fmt}"

    filters: list[str] = []
    if speed != 1.0:
        filters.append(f"setpts={1.0 / speed:g}*PTS")
    filters.append(f"fps={fps}")
    if width is not None:
        filters.append(f"scale={width}:-1:flags=lanczos")
    vf_base = ",".join(filters)

    if fmt == "gif":
        _make_gif(source, start, end, output, vf_base, loop)
    else:
        _make_webp(source, start, end, output, vf_base, loop)

    return output


def _make_gif(source: Path, start: str, end: str, output: Path, vf_base: str, loop: int) -> None:
    """Generate a GIF via two-pass palette encoding.

    Pass 1 builds an optimised palette from the source frames; pass 2 uses it
    to dither the output, which eliminates the washed-out colours of a naive GIF
    encode.

    Args:
        source: Input video file.
        start: Segment start timestamp.
        end: Segment end timestamp.
        output: Destination GIF path.
        vf_base: Base video filter (fps + optional scale).
        loop: Number of times to loop; 0 = infinite.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        palette = Path(tmp.name)

    try:
        run_ffmpeg(["-ss", start, "-to", end, "-i", str(source), "-vf", f"{vf_base},palettegen", str(palette)])
        run_ffmpeg(
            [
                "-ss",
                start,
                "-to",
                end,
                "-i",
                str(source),
                "-i",
                str(palette),
                "-filter_complex",
                f"{vf_base} [x]; [x][1:v] paletteuse",
                "-loop",
                str(loop),
                str(output),
            ]
        )
    finally:
        palette.unlink(missing_ok=True)


def _make_webp(source: Path, start: str, end: str, output: Path, vf_base: str, loop: int) -> None:
    """Generate an animated WebP.

    Args:
        source: Input video file.
        start: Segment start timestamp.
        end: Segment end timestamp.
        output: Destination WebP path.
        vf_base: Base video filter (fps + optional scale).
        loop: Number of times to loop; 0 = infinite.
    """
    run_ffmpeg(
        [
            "-ss",
            start,
            "-to",
            end,
            "-i",
            str(source),
            "-vf",
            vf_base,
            "-vcodec",
            "libwebp",
            "-loop",
            str(loop),
            str(output),
        ]
    )


_EXAMPLES = """
examples:
  uv run main.py av.to_anim clip.mp4 00:00:05 00:00:10
  uv run main.py av.to_anim clip.mp4 1:30 1:45 --format webp --width 480
  uv run main.py av.to_anim clip.mp4 0 5 --fps 24 --filename result
  uv run main.py av.to_anim clip.mp4 0 10 --speed 2.0
  uv run main.py av.to_anim clip.mp4 0 5 --speed 0.5
  uv run main.py av.to_anim clip.mp4 0 5 --loop 3
"""


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to to_anim()."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.to_anim",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="Source video file")
    parser.add_argument("start", help="Start timestamp (e.g. 00:00:05, 1:30, or 5.0)")
    parser.add_argument("end", help="End timestamp")
    parser.add_argument(
        "--format",
        dest="fmt",
        default="gif",
        choices=FORMATS,
        help="Output format (default: gif)",
    )
    parser.add_argument("--fps", type=int, default=15, help="Frame rate (default: 15)")
    parser.add_argument(
        "--width", type=int, default=None, metavar="PX", help="Output width in pixels (height auto-scaled)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        metavar="X",
        help="Playback speed multiplier: 2.0 = twice as fast, 0.5 = half speed (default: 1.0)",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        metavar="N",
        help="Number of times to loop; 0 = infinite (default: 0)",
    )
    parser.add_argument("--filename", default=None, metavar="NAME", help="Output file stem (defaults to source stem)")
    parser.add_argument(
        "--outputs", type=Path, default=None, metavar="DIR", help="Output directory (default: av/outputs/)"
    )
    args = parser.parse_args()

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        output = to_anim(
            args.source,
            args.start,
            args.end,
            outputs_dir,
            fmt=args.fmt,
            fps=args.fps,
            width=args.width,
            speed=args.speed,
            loop=args.loop,
            filename=args.filename,
        )
        print(output)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
