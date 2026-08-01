"""Icon lookup for scripts and file categories in the Drop-to-Discover chooser.

Values are glyph *names* from ``webapp/templates/_icons.html``, not URLs. The
browser renders them from the inline sprite that ``base.html`` emits, so an
icon costs no request and tints with ``currentColor``.

Entries absent from these maps resolve to ``None``, which templates render as a
neutral placeholder glyph, so an unmapped script degrades visibly rather than
showing nothing at all.
"""

SCRIPT_ICONS: dict[str, str] = {
    "av.dump_frames": "frames",
    "av.filmstrip": "film",
    "av.join": "merge",
    "av.split": "split",
    "av.tag": "tag",
    "av.to_anim": "gif",
    "av.trim": "scissors",
    "av.video_crop": "crop",
    "av.volume": "volume",
    "formats.convert_audio": "file-audio",
    "formats.convert_docs": "file-text",
    "formats.convert_image": "image",
    "formats.convert_tabular": "table",
    "formats.convert_video": "file-video",
    "gif.make_gif": "gif",
    "photo.remove_bg": "camera",
    "speech.transcribe": "mic",
}

CATEGORY_ICONS: dict[str, str] = {
    "audio": "file-audio",
    "document": "file-text",
    "image": "image",
    "tabular": "table",
    "video": "file-video",
}


def icon_for_script(key: str) -> str | None:
    """Return the icon name for a script key.

    Args:
        key: Dotted script key such as ``"photo.remove_bg"``.

    Returns:
        A glyph name defined in ``_icons.html``, or None when the script has
        no icon assigned.
    """
    return SCRIPT_ICONS.get(key)


def icon_for_category(category: str | None) -> str | None:
    """Return the icon name for a file category.

    Args:
        category: Category name such as ``"audio"``, or None.

    Returns:
        A glyph name defined in ``_icons.html``, or None when the category is
        unknown.
    """
    return CATEGORY_ICONS.get(category or "")
