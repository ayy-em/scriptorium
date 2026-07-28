"""Compatibility badges shown on script pages.

Badges are derived from data the scripts already publish — the ``ACCEPTS``
attribute and the shape of the argparse file input — plus a small map of the
external tools a theme drives. Nothing here asks scripts to declare new
metadata; richer per-script tags are tracked in BACKLOG.md.
"""

from types import ModuleType

from webapp._form import FieldSpec, accepts_directory, file_input_for

# External binaries a script shells out to. Keyed by dotted script key first,
# then by theme, so a single script can override its theme's default.
_TOOL_BY_KEY: dict[str, str] = {
    "formats.convert_audio": "ffmpeg",
    "formats.convert_video": "ffmpeg",
}

_TOOL_BY_THEME: dict[str, str] = {
    "av": "ffmpeg",
    "downloads": "yt-dlp",
}

# Order badges are rendered in, so two scripts never list the same set
# differently. Anything unlisted sorts last, alphabetically.
_ORDER = ["video", "audio", "image", "document", "tabular", "batch", "ffmpeg", "yt-dlp"]


def _sort_key(badge: str) -> tuple[int, str]:
    """Return a stable sort key placing known badges in ``_ORDER``.

    Args:
        badge: A badge label.

    Returns:
        Tuple of (rank, label) — unknown badges rank after known ones.
    """
    return (_ORDER.index(badge) if badge in _ORDER else len(_ORDER), badge)


def badges_for(key: str, mod: ModuleType, specs: list[FieldSpec]) -> list[str]:
    """Return the compatibility badges for one script.

    Args:
        key: Dotted script key such as ``"av.filmstrip"``.
        mod: The imported script module.
        specs: Field descriptors from ``fields_from_parser()``.

    Returns:
        Ordered, de-duplicated badge labels. Empty when the script publishes no
        ``ACCEPTS`` set, takes no directory input, and drives no known tool.
    """
    found: set[str] = set(getattr(mod, "ACCEPTS", set()))

    if accepts_directory(file_input_for(specs)):
        found.add("batch")

    theme = key.split(".", 1)[0]
    tool = _TOOL_BY_KEY.get(key) or _TOOL_BY_THEME.get(theme)
    if tool:
        found.add(tool)

    return sorted(found, key=_sort_key)
