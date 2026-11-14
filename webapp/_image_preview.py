"""A picture the browser can always show, in the pixels a crop will use.

The crop page draws its box on an image, and the box has to mean the same
pixels to the script that cuts it. Serving the staged file as-is fails that two
ways: no desktop browser decodes HEIC, which is what most phones write, and the
browser's own EXIF handling is not something the server can see. So the page
draws on this instead — the image ``core.images.open_upright`` produces, the
same one ``photo.crop`` cuts — scaled down so a 48-megapixel photo does not
travel to the page at full size. The full upright size goes alongside, so the
page can measure its box in real image pixels rather than preview pixels.
"""

from dataclasses import dataclass
import io
from pathlib import Path

from PIL import Image

from core.images import open_upright

#: Longest side of the preview, in pixels. Enough for a sharp editor on a
#: large screen; the box itself is kept in full-size image pixels.
MAX_SIDE = 2048

_JPEG_QUALITY = 88


class PreviewError(Exception):
    """The file could not be opened as an image."""


@dataclass(frozen=True)
class Preview:
    """An encoded preview and the size of the image it stands for.

    Attributes:
        data: Encoded image bytes.
        media_type: MIME type of *data*.
        width: Width of the full upright image.
        height: Height of the full upright image.
    """

    data: bytes
    media_type: str
    width: int
    height: int


def render_preview(path: Path, max_side: int = MAX_SIDE) -> Preview:
    """Encode an upright, size-capped copy of an image.

    Args:
        path: Image file.
        max_side: Longest side the preview may have.

    Returns:
        The preview, as JPEG — or PNG when the image has transparency, so the
        page shows what the crop will keep.

    Raises:
        PreviewError: When the file is not an image Pillow can open.
    """
    try:
        image = open_upright(path)
        image.load()
    except (OSError, ValueError) as e:
        raise PreviewError(f"Cannot read {path.name} as an image: {e}") from e
    width, height = image.size
    preview = image.copy()
    preview.thumbnail((max_side, max_side))

    buffer = io.BytesIO()
    if _has_alpha(preview):
        preview.convert("RGBA").save(buffer, format="PNG")
        media_type = "image/png"
    else:
        preview.convert("RGB").save(buffer, format="JPEG", quality=_JPEG_QUALITY)
        media_type = "image/jpeg"
    return Preview(buffer.getvalue(), media_type, width, height)


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA", "PA"} or (image.mode == "P" and "transparency" in image.info)
