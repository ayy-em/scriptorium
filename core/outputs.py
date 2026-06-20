"""Standardized output path resolution for all scripts."""

from datetime import datetime
from pathlib import Path

from core.paths import outputs_dir


def default_stem() -> str:
    """Return a timestamp-based default filename stem.

    Returns:
        String in ``YYYYMMDD_HHmm`` format, e.g. ``'20260620_1505'``.
    """
    return datetime.now().strftime("%Y%m%d_%H%M")


def deduplicate(path: Path) -> Path:
    """Return a collision-free variant of *path*.

    If *path* does not exist it is returned unchanged.  Otherwise ``_001``,
    ``_002``, ... is appended to the stem until a free slot is found.

    Args:
        path: Candidate output file path.

    Returns:
        The first available path with the same parent and extension.

    Raises:
        FileExistsError: If all 999 suffixed variants already exist.
    """
    if not path.exists():
        return path
    for i in range(1, 1000):
        candidate = path.with_stem(f"{path.stem}_{i:03d}")
        if not candidate.exists():
            return candidate
    raise FileExistsError(f"all 999 suffixed variants of {path.name} already exist")


def resolve_output(
    output: str | Path | None,
    *,
    theme: str,
    ext: str,
    makedirs: bool = True,
) -> Path:
    """Resolve user-provided ``--output`` to a concrete, collision-free path.

    Resolution rules based on what the user supplies:

    * **Nothing** (``None``): default outputs dir + ``YYYYMMDD_HHmm.ext``.
    * **Existing directory**: that directory + ``YYYYMMDD_HHmm.ext``.
    * **Path with file extension**: treated as a file specification.

      - Bare filename (no directory part): placed in the default outputs dir.
      - Full path: used as-is.

    * **Path without extension** (and not an existing directory): treated as a
      new directory + ``YYYYMMDD_HHmm.ext``.

    Args:
        output: Raw ``--output`` value, or ``None`` for full defaults.
        theme: Script theme slug for the default output directory.
        ext: File extension including the leading dot (e.g. ``".pdf"``).
        makedirs: Create parent directories when they do not exist.

    Returns:
        Collision-free output ``Path``.
    """
    ext = ext if ext.startswith(".") else f".{ext}"
    stamp = default_stem()

    if output is None:
        path = outputs_dir(theme) / f"{stamp}{ext}"
    else:
        p = Path(output)
        if p.is_dir():
            path = p / f"{stamp}{ext}"
        elif p.suffix:
            path = p if p.parent != Path(".") else outputs_dir(theme) / p
        else:
            path = p / f"{stamp}{ext}"

    if makedirs:
        path.parent.mkdir(parents=True, exist_ok=True)

    return deduplicate(path)


def resolve_output_dir(
    output: str | Path | None,
    *,
    theme: str,
    makedirs: bool = True,
) -> Path:
    """Resolve user-provided ``--output`` to an output directory.

    For multi-output scripts that produce several files.  If the user passes a
    file path (has an extension), the parent directory is used.

    Args:
        output: Raw ``--output`` value, or ``None`` for the theme default.
        theme: Script theme slug for the default output directory.
        makedirs: Create the directory when it does not exist.

    Returns:
        Resolved directory ``Path``.
    """
    if output is None:
        d = outputs_dir(theme)
    else:
        p = Path(output)
        if p.is_dir():
            d = p
        elif p.suffix:
            d = outputs_dir(theme) if p.parent == Path(".") else p.parent
        else:
            d = p

    if makedirs:
        d.mkdir(parents=True, exist_ok=True)
    return d
