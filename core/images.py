"""Make Pillow read every format ``IMAGE_EXTS`` promises.

HEIC/HEIF — what every iPhone and most Android cameras write — is not in
Pillow's own decoder set. ``pillow-heif`` adds it by registering an opener,
after which ``Image.open`` handles a ``.heic`` like any other file. Every
script that opens images with Pillow calls ``ensure_image_formats()`` first,
so the extension list in ``scripts/formats/_utils.py`` and what actually opens
cannot drift apart.

Two HEIC facts worth stating rather than discovering: a Live Photo or burst
opens as its primary still, the motion track is ignored; and orientation
lives in EXIF far more often than for JPEG, so callers that write to a format
without EXIF (PNG, WebP) must bake it in with ``ImageOps.exif_transpose``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from PIL import Image

_REGISTERED = False


def ensure_image_formats() -> None:
    """Register the HEIF opener with Pillow, once.

    Silently a no-op when ``pillow-heif`` is not installed: the scripts then
    behave as before the format was added, and a ``.heic`` fails at
    ``Image.open`` with Pillow's own "cannot identify image file".
    """
    global _REGISTERED  # noqa: PLW0603
    if _REGISTERED:
        return
    try:
        from pillow_heif import register_heif_opener  # noqa: PLC0415
    except ImportError:
        return
    register_heif_opener()
    _REGISTERED = True


def open_upright(path: Path) -> Image.Image:
    """Open an image with its EXIF orientation applied.

    A portrait phone photo is stored on its side with an orientation tag.
    Anything that shows an image and then acts on coordinates picked on it —
    ``photo.crop`` and the preview the crop page draws on — must use the same
    upright pixels, or a box drawn on the picture lands somewhere else.

    Args:
        path: Image file.

    Returns:
        The image, rotated and flipped as its EXIF says.
    """
    from PIL import Image, ImageOps  # noqa: PLC0415

    ensure_image_formats()
    return ImageOps.exif_transpose(Image.open(path))
