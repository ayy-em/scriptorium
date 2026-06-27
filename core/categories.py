"""Central file-category registry used by Drop-to-Discover.

Maps file extensions to semantic categories (video, audio, image, …) so the
UI can look up which scripts accept a given file type.
"""

from __future__ import annotations

from pathlib import PurePath

from scripts.formats._utils import AUDIO_EXTS, IMAGE_EXTS, TABULAR_EXTS, VIDEO_EXTS
from scripts.formats.convert_docs import DOCS_EXTS

CATEGORY_EXTS: dict[str, frozenset[str]] = {
    "video": VIDEO_EXTS,
    "audio": AUDIO_EXTS,
    "image": IMAGE_EXTS,
    "tabular": TABULAR_EXTS,
    "document": DOCS_EXTS,
}

EXT_TO_CATEGORY: dict[str, str] = {ext: cat for cat, exts in CATEGORY_EXTS.items() for ext in exts}


def categorize(filename: str) -> str | None:
    """Return the category for *filename* based on its extension, or ``None``.

    Args:
        filename: A filename or path string whose suffix is inspected.

    Returns:
        Category name (e.g. ``"video"``) or ``None`` if unrecognised.
    """
    suffix = PurePath(filename).suffix.lower()
    return EXT_TO_CATEGORY.get(suffix)
