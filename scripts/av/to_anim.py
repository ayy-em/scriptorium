"""CLI and programmatic interface for converting a video segment to animated GIF or WebP."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from scripts.av._utils import av_inputs_dir, av_outputs_dir, probe_streams, run_ffmpeg

TITLE = "Turn a video segment into an animated GIF/WebP"
DESCRIPTION = "Convert a video segment to an animated GIF or WebP given start/end timestamps."

FORMATS = ("gif", "webp")

# Maximum output dimensions, chosen by orientation.
_LANDSCAPE_CAP = (1920, 1080)
_PORTRAIT_CAP = (720, 1600)
_SD_MAX_W = 600
_SD_MAX_H = 720
_SD_MAX_FPS = 15


def _get_video_dims(source: Path) -> tuple[int, int] | None:
    """Return effective (width, height) of the first video stream, or None if undetermined.

    Accounts for rotation metadata (common in phone-recorded videos): if the
    stream is tagged with 90 or 270 degree rotation, width and height are swapped
    to reflect the displayed orientation.
    """
    try:
        for stream in probe_streams(source):
            if stream.get("codec_type") == "video":
                w, h = stream.get("width"), stream.get("height")
                if w and h:
                    w, h = int(w), int(h)
                    rotation = _stream_rotation(stream)
                    if rotation in (90, 270):
                        w, h = h, w
                    return w, h
    except Exception:
        pass
    return None


def _stream_rotation(stream: dict) -> int:
    """Extract rotation degrees from a video stream's metadata."""
    rot = stream.get("tags", {}).get("rotate", "0")
    try:
        return abs(int(rot)) % 360
    except (ValueError, TypeError):
        pass
    for sd in stream.get("side_data_list", []):
        rot = sd.get("rotation", 0)
        try:
            return abs(int(rot)) % 360
        except (ValueError, TypeError):
            continue
    return 0


def _cap_scale_filter(
    src_w: int, src_h: int, user_width: int | None, cap: tuple[int, int] | None = None
) -> str | None:
    """Return an ffmpeg scale filter that fits output within the resolution cap.

    Picks the cap based on orientation: 1920x1080 for landscape/square,
    720x1600 for portrait. Never upscales. Uses -2 for height so ffmpeg
    auto-rounds to the nearest even number.

    Args:
        src_w: Source video width in pixels.
        src_h: Source video height in pixels.
        user_width: User-requested output width, or None.
        cap: Explicit (max_w, max_h) override; defaults to orientation-based cap.

    Returns:
        Scale filter string (e.g. "scale=960:-2:flags=lanczos"), or None if
        the source already fits within the effective bounds.
    """
    if cap is None:
        cap = _PORTRAIT_CAP if src_h > src_w else _LANDSCAPE_CAP
    cap_w, cap_h = cap
    max_w = min(user_width, cap_w) if user_width is not None else cap_w

    fit_scale = min(max_w / src_w, cap_h / src_h)

    if fit_scale >= 1.0:
        if user_width is None or user_width >= src_w:
            return None
        out_w = (user_width // 2) * 2
        return f"scale={out_w}:-2:flags=lanczos"

    out_w = max(2, (int(src_w * fit_scale) // 2) * 2)
    return f"scale={out_w}:-2:flags=lanczos"


def _sd_scale_filter(src_w: int, src_h: int) -> str | None:
    """Return an ffmpeg scale filter for SD mode. Never upscales.

    Portrait (h > w): constrain height to 720, auto width.
    Landscape/square: constrain width to 600, auto height.
    """
    if src_h > src_w:
        if src_h <= _SD_MAX_H:
            return None
        target_h = (_SD_MAX_H // 2) * 2
        return f"scale=-2:{target_h}:flags=lanczos"
    if src_w <= _SD_MAX_W:
        return None
    target_w = (_SD_MAX_W // 2) * 2
    return f"scale={target_w}:-2:flags=lanczos"


def to_anim(  # noqa: PLR0912, PLR0913
    source: Path,
    start: str | None = None,
    end: str | None = None,
    outputs_dir: Path | None = None,
    *,
    fmt: str = "webp",
    fps: int = 15,
    width: int | None = None,
    speed: float = 1.0,
    loop: int = 0,
    filename: str | None = None,
    sd: bool = False,
    optimize_gif: bool = False,
) -> Path:
    """Convert a video (or segment) to an animated GIF or WebP.

    GIF output uses a two-pass palette approach (palettegen then paletteuse) for
    significantly better colour quality than a single-pass encode. WebP is a
    single-pass encode with libwebp. Both formats require FFmpeg on PATH.

    Output is automatically capped at 1920x1080 (landscape) or 720x1600 (portrait)
    to keep file sizes manageable. Pass --width to constrain further, or --sd to
    cap at 600x720.

    Timestamps are passed directly to ffmpeg and accept any format it understands:
    HH:MM:SS, HH:MM:SS.ms, or bare seconds (e.g. "5", "1:30", "00:01:30.500").
    When omitted, the full video is converted.

    Speed is applied via a setpts filter (setpts=(1/speed)*PTS) before the fps
    filter, so --speed 2.0 plays back at 2x and --speed 0.5 plays at half speed.

    Args:
        source: Source video file.
        start: Start timestamp. Defaults to beginning of video.
        end: End timestamp. Defaults to end of video.
        outputs_dir: Directory where the output file is written. Defaults to av/outputs/.
        fmt: Output format — "gif" or "webp". Defaults to "webp".
        fps: Frame rate of the output animation. Defaults to 15.
        width: Max output width in pixels; subject to orientation cap. Defaults to cap.
        speed: Playback speed multiplier. 2.0 = twice as fast, 0.5 = half speed. Defaults to 1.0.
        loop: Number of times to loop. 0 = infinite. Defaults to 0.
        filename: Output file stem (no extension). Defaults to the source file stem.
        sd: Cap output at 600x720 for smaller file sizes. Defaults to False.
        optimize_gif: Aggressively optimize GIF size (fewer colors, diff-rect encoding,
            gifsicle post-processing when available). Defaults to False.

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

    if outputs_dir is None:
        outputs_dir = av_outputs_dir()
    outputs_dir.mkdir(parents=True, exist_ok=True)

    time_args: list[str] = []
    if start is not None:
        time_args += ["-ss", start]
    if end is not None:
        time_args += ["-to", end]

    stem = filename or source.stem
    output = outputs_dir / f"{stem}.{fmt}"

    if sd:
        fps = min(fps, _SD_MAX_FPS)

    filters: list[str] = []
    if speed != 1.0:
        filters.append(f"setpts={1.0 / speed:g}*PTS")
    filters.append(f"fps={fps}")

    dims = _get_video_dims(source)
    if sd and dims is not None:
        scale = _sd_scale_filter(*dims)
    elif dims is not None:
        scale = _cap_scale_filter(*dims, width)
    elif width is not None:
        scale = f"scale={width}:-2:flags=lanczos"
    else:
        scale = None
    if scale:
        filters.append(scale)

    vf_base = ",".join(filters)

    if fmt == "gif":
        _make_gif(source, time_args, output, vf_base, loop, optimize=optimize_gif)
    else:
        _make_webp(source, time_args, output, vf_base, loop)

    return output


def _make_gif(
    source: Path,
    time_args: list[str],
    output: Path,
    vf_base: str,
    loop: int,
    *,
    optimize: bool = False,
) -> None:
    """Generate a GIF via two-pass palette encoding.

    Pass 1 builds a palette with stats_mode=diff, which optimises colours for
    frame-to-frame transitions rather than individual frames — this significantly
    reduces banding in animated content. Pass 2 uses the palette to dither the output.

    When optimize=True: palette is capped at 128 colors, paletteuse encodes only
    changed rectangles per frame with bayer dithering, and gifsicle --lossy
    post-processing is applied if gifsicle is on PATH.

    Args:
        source: Input video file.
        time_args: ffmpeg seek/trim flags (e.g. ["-ss", "5", "-to", "10"]), may be empty.
        output: Destination GIF path.
        vf_base: Base video filter (speed + fps + optional scale).
        loop: Number of times to loop; 0 = infinite.
        optimize: Aggressively optimize for file size.
    """
    palettegen = "palettegen=stats_mode=diff"
    paletteuse = "paletteuse"
    if optimize:
        palettegen = "palettegen=max_colors=128:stats_mode=diff"
        paletteuse = "paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle"

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        palette = Path(tmp.name)

    palette_vf = f"{vf_base},format=rgb24,{palettegen}"
    try:
        run_ffmpeg(
            ["-v", "error", *time_args, "-i", str(source), "-vf", palette_vf, "-update", "1", str(palette)]
        )
        run_ffmpeg(
            [
                *time_args,
                "-i",
                str(source),
                "-i",
                str(palette),
                "-filter_complex",
                f"{vf_base} [x]; [x][1:v] {paletteuse}",
                "-loop",
                str(loop),
                str(output),
            ]
        )
    finally:
        palette.unlink(missing_ok=True)

    if optimize:
        _gifsicle_optimize(output)


def _gifsicle_optimize(path: Path) -> None:
    """Run gifsicle --lossy in-place if available; skip silently otherwise."""
    if shutil.which("gifsicle") is None:
        print("gifsicle not found on PATH, skipping post-optimization", file=sys.stderr)
        return
    subprocess.run(
        ["gifsicle", "-O3", "--lossy=80", "--batch", str(path)],
        check=True,
    )


def _make_webp(
    source: Path, time_args: list[str], output: Path, vf_base: str, loop: int
) -> None:
    """Generate an animated WebP.

    Uses quality=80 and compression_level=6 for a good size/quality balance.
    Lossless WebP at default quality produces files comparable in size to
    unoptimised GIFs; these settings cut that substantially.

    Args:
        source: Input video file.
        time_args: ffmpeg seek/trim flags (e.g. ["-ss", "5", "-to", "10"]), may be empty.
        output: Destination WebP path.
        vf_base: Base video filter (speed + fps + optional scale).
        loop: Number of times to loop; 0 = infinite.
    """
    run_ffmpeg(
        [
            *time_args,
            "-i",
            str(source),
            "-vf",
            vf_base,
            "-vcodec",
            "libwebp",
            "-quality",
            "80",
            "-compression_level",
            "6",
            "-loop",
            str(loop),
            str(output),
        ]
    )


_EXAMPLES = """
examples:
  uv run main.py av.to_anim clip.mp4
  uv run main.py av.to_anim clip.mp4 00:00:05 00:00:10
  uv run main.py av.to_anim clip.mp4 1:30 1:45 --format gif --width 480
  uv run main.py av.to_anim clip.mp4 0 5 --fps 24 --filename result
  uv run main.py av.to_anim clip.mp4 0 10 --speed 2.0
  uv run main.py av.to_anim clip.mp4 0 10 --sd
  uv run main.py av.to_anim clip.mp4 --format gif --gif-optimize
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.to_anim",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("source", type=Path, help="Source video file (bare filename resolves to av/inputs/)")
    parser.add_argument("start", nargs="?", default=None, help="Start timestamp (default: beginning of video)")
    parser.add_argument("end", nargs="?", default=None, help="End timestamp (default: end of video)")
    parser.add_argument(
        "--format",
        dest="fmt",
        default="webp",
        choices=FORMATS,
        help="Output format (default: webp)",
    )
    parser.add_argument("--fps", type=int, default=15, help="Frame rate (default: 15)")
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        metavar="PX",
        help="Max output width in pixels; capped by orientation limit (default: cap)",
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
    parser.add_argument("--sd", action="store_true", help="Cap output at 600x720 for smaller file sizes")
    parser.add_argument(
        "--gif-optimize",
        action="store_true",
        help="Aggressively optimize GIF size (128 colors, diff-rect encoding, gifsicle if available)",
    )
    parser.add_argument(
        "--outputs", type=Path, default=None, metavar="DIR", help="Output directory (default: av/outputs/)"
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to to_anim()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = av_inputs_dir() / source.name

    outputs_dir = args.outputs or av_outputs_dir()

    try:
        output = to_anim(
            source,
            args.start,
            args.end,
            outputs_dir,
            fmt=args.fmt,
            fps=args.fps,
            width=args.width,
            speed=args.speed,
            loop=args.loop,
            filename=args.filename,
            sd=args.sd,
            optimize_gif=args.gif_optimize,
        )
        print(output)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
