from pathlib import Path
import re

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif"})
IMG_NAME_RE = re.compile(r"^img_\d+$")


def find_images(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def find_captions(directory: Path) -> list[Path]:
    return sorted(p for p in directory.iterdir() if p.suffix.lower() == ".txt")
