"""Icon lookup for scripts and file categories in the Drop-to-Discover chooser.

Icons live in ``webapp/static/icons`` as PNGs. Entries absent from these maps
resolve to ``None``, which templates render as a neutral placeholder glyph, so
an unmapped script degrades visibly rather than showing a broken image.

See MISSING_ICONS for the artwork still to be supplied.
"""

ICON_URL_PREFIX = "/static/icons"

SCRIPT_ICONS: dict[str, str] = {
    "formats.convert_audio": "icon-audio.png",
    "formats.convert_docs": "icon-doc.png",
    "formats.convert_image": "icon-image.png",
    "formats.convert_tabular": "icon-spreadsheet.png",
    "photo.remove_bg": "icon-camera.png",
    "speech.transcribe": "icon-speech.png",
}

CATEGORY_ICONS: dict[str, str] = {
    "audio": "icon-audio.png",
    "document": "icon-doc.png",
    "image": "icon-image.png",
    "tabular": "icon-spreadsheet.png",
}

# Artwork not yet supplied; these render the placeholder glyph until added.
MISSING_ICONS: dict[str, str] = {
    "av.dump_frames": "icon-frames.png",
    "av.filmstrip": "icon-filmstrip.png",
    "av.join": "icon-join.png",
    "av.split": "icon-split.png",
    "av.tag": "icon-tag.png",
    "av.to_anim": "icon-gif.png",
    "av.trim": "icon-trim.png",
    "av.video_crop": "icon-crop.png",
    "av.volume": "icon-volume.png",
    "formats.convert_video": "icon-convert.png",
    "gif.make_gif": "icon-gif.png",
    "video": "icon-video.png",
}


def icon_for_script(key: str) -> str | None:
    """Return the icon URL for a script key.

    Args:
        key: Dotted script key such as ``"photo.remove_bg"``.

    Returns:
        Absolute URL under /static, or None when no artwork exists yet.
    """
    name = SCRIPT_ICONS.get(key)
    return f"{ICON_URL_PREFIX}/{name}" if name else None


def icon_for_category(category: str | None) -> str | None:
    """Return the icon URL for a file category.

    Args:
        category: Category name such as ``"audio"``, or None.

    Returns:
        Absolute URL under /static, or None when no artwork exists yet.
    """
    name = CATEGORY_ICONS.get(category or "")
    return f"{ICON_URL_PREFIX}/{name}" if name else None
