"""Filmstrip sheet from a video: evenly-spaced frames arranged on a flexible canvas."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import platform
import sys
import tempfile
from typing import TYPE_CHECKING

from scripts.av._utils import av_inputs_dir, av_outputs_dir, run_ffmpeg, run_ffprobe

if TYPE_CHECKING:
    from PIL import ImageDraw as _ImageDrawModule
    from PIL import ImageFont as _ImageFontModule

TITLE = "Video filmstrip sheet"
DESCRIPTION = "Extract frames from a video and arrange them on a filmstrip sheet (PDF or PNG)."

_GRIDS: dict[str, tuple[int, int]] = {
    "2x2": (2, 2),
    "2x3": (2, 3),
    "3x3": (3, 3),
    "3x4": (3, 4),
    "3x5": (3, 5),
    "4x4": (4, 4),
    "4x5": (4, 5),
    "5x5": (5, 5),
}

_PAD = 30
_GAP = 10
_HEADER_H = 56
_SHADOW_LINES = [(237, 237, 237), (243, 243, 243), (248, 248, 248)]
_BG = (250, 250, 250)
_HEADER_BG = (200, 200, 200)
_HEADER_BORDER = (190, 190, 190)
_FRAME_BOX_LANDSCAPE = (400, 300)
_FRAME_BOX_PORTRAIT = (180, 400)
_LABEL_H = 20

_EXAMPLES = """
examples:
  uv run main.py av.filmstrip video.mp4
  uv run main.py av.filmstrip video.mp4 --grid 3x4 --offset 30
  uv run main.py av.filmstrip video.mp4 --output my_sheet --format png
  uv run main.py av.filmstrip video.mp4 --grid 2x3 --format pdf
"""


def filmstrip(
    source: Path,
    grid: str = "3x3",
    offset: float = 0.0,
    output_name: str | None = None,
    fmt: str = "pdf",
    outputs_dir: Path | None = None,
) -> Path:
    """Extract frames from a video and composite them onto a filmstrip sheet.

    Canvas dimensions adapt to the video's native aspect ratio and the chosen
    grid layout.  A header bar shows the filename, runtime, creation timestamp,
    and branding.

    Returns:
        Path to the saved filmstrip file.
    """
    from PIL import Image, ImageDraw  # noqa: PLC0415

    if grid not in _GRIDS:
        raise ValueError(f"unsupported grid '{grid}', choose from: {', '.join(_GRIDS)}")
    rows, cols = _GRIDS[grid]
    num_strips = rows * cols

    duration, vid_w, vid_h = _probe_video(source)
    effective = duration - offset
    if effective <= 0:
        raise ValueError(f"offset ({offset}s) >= video duration ({duration:.1f}s)")

    stem = output_name or source.stem
    out_dir = outputs_dir or av_outputs_dir()
    out_path = out_dir / f"{stem}.{fmt}"

    positions = [offset + (i + 0.5) * effective / num_strips for i in range(num_strips)]

    box_w, box_h = _FRAME_BOX_LANDSCAPE if vid_w >= vid_h else _FRAME_BOX_PORTRAIT
    scale = min(box_w / vid_w, box_h / vid_h)
    frame_w = round(vid_w * scale)
    frame_h = round(vid_h * scale)

    cell_h = frame_h + _LABEL_H
    canvas_w = 2 * _PAD + cols * frame_w + (cols - 1) * _GAP
    shadow_h = len(_SHADOW_LINES)
    grid_top = _HEADER_H + 1 + shadow_h + _PAD
    canvas_h = grid_top + rows * cell_h + (rows - 1) * _GAP + _PAD

    canvas = Image.new("RGB", (canvas_w, canvas_h), _BG)
    draw = ImageDraw.Draw(canvas)
    label_font = _load_font(16)

    _draw_header(draw, canvas_w, source.name, duration)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for idx, seek in enumerate(positions):
            frame_path = tmp_dir / f"frame_{idx:03d}.jpg"
            run_ffmpeg([
                "-ss", f"{seek:.3f}",
                "-i", str(source),
                "-frames:v", "1",
                "-update", "1",
                "-q:v", "2",
                str(frame_path),
            ])
            frame = Image.open(frame_path)
            frame.thumbnail((frame_w, frame_h), Image.LANCZOS)
            col = idx % cols
            row = idx // cols
            x = _PAD + col * (frame_w + _GAP) + (frame_w - frame.width) // 2
            y = grid_top + row * (cell_h + _GAP) + (frame_h - frame.height) // 2
            canvas.paste(frame, (x, y))

            label = _format_duration(seek)
            label_x = _PAD + col * (frame_w + _GAP) + frame_w // 2
            label_y = grid_top + row * (cell_h + _GAP) + frame_h + 4
            label_w = draw.textlength(label, font=label_font)
            draw.text((label_x - label_w / 2, label_y), label, fill=(130, 130, 138), font=label_font)

    if fmt == "pdf":
        canvas.save(str(out_path), "PDF", resolution=150)
    else:
        canvas.save(str(out_path), "PNG")

    return out_path


def _draw_header(draw: _ImageDrawModule.ImageDraw, canvas_w: int, filename: str, duration: float) -> None:
    """Render the header bar with file info, timestamp, and branding."""
    draw.rectangle([(0, 0), (canvas_w, _HEADER_H - 1)], fill=_HEADER_BG)
    draw.line([(0, _HEADER_H), (canvas_w, _HEADER_H)], fill=_HEADER_BORDER, width=1)
    for i, color in enumerate(_SHADOW_LINES):
        y = _HEADER_H + 1 + i
        draw.line([(0, y), (canvas_w, y)], fill=color)

    font = _load_font(22)
    font_sm = _load_font(13)

    dur_str = _format_duration(duration)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    left = f"{filename}   {dur_str}"
    right = f"Created on {now_str} using Scriptorium"

    text_y = (_HEADER_H - 22) // 2
    draw.text((_PAD, text_y), left, fill=(40, 40, 44), font=font)

    right_w = draw.textlength(right, font=font_sm)
    draw.text((canvas_w - _PAD - right_w, (_HEADER_H - 13) // 2), right, fill=(110, 110, 118), font=font_sm)


def _probe_video(file: Path) -> tuple[float, int, int]:
    """Return (duration_secs, width, height) for a video file."""
    data = run_ffprobe(["-show_format", "-show_streams", str(file)])
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise ValueError(f"Cannot determine duration of {file}")
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video":
            return float(duration), int(stream["width"]), int(stream["height"])
    raise ValueError(f"No video stream found in {file}")


def _format_duration(seconds: float) -> str:
    """Format seconds as 00h00m00s, omitting hours when zero."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h:02d}h{m:02d}m{s:02d}s"
    return f"{m:02d}m{s:02d}s"


def _load_font(size: int) -> _ImageFontModule.FreeTypeFont:
    """Try system fonts, fall back to Pillow default."""
    from PIL import ImageFont  # noqa: PLC0415

    candidates: list[str] = []
    system = platform.system()
    if system == "Windows":
        candidates = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/arial.ttf"]
    elif system == "Darwin":
        candidates = ["/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc"]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
        ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.filmstrip",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Video file (bare name resolves to av/inputs/)",
    )
    parser.add_argument(
        "--grid",
        choices=sorted(_GRIDS),
        default="3x3",
        help="Frame grid layout, rows x cols (default: 3x3)",
    )
    parser.add_argument(
        "--offset",
        type=float,
        default=0.0,
        metavar="SECS",
        help="Seconds to skip at the start of the video (default: 0)",
    )
    parser.add_argument(
        "--output",
        metavar="NAME",
        help="Output filename stem, no extension (default: video filename stem)",
    )
    parser.add_argument(
        "--format",
        choices=["pdf", "png"],
        default="pdf",
        help="Output format (default: pdf)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to filmstrip()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = av_inputs_dir() / source.name

    try:
        out = filmstrip(
            source,
            grid=args.grid,
            offset=args.offset,
            output_name=args.output,
            fmt=args.format,
        )
        print(out)
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
