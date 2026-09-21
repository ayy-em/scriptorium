"""Standardized output path resolution for all scripts."""

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from core.invocation import is_webapp_run
from core.paths import outputs_dir, outputs_root


def _default_output_dir(theme: str) -> Path:
    """Return where output goes when the user did not say.

    The web UI reads results out of the managed outputs tree, so that has to
    stay its default. A person at a terminal expects a tool to write where they
    are standing, not into a directory they would have to go looking for.

    Args:
        theme: Script theme slug.

    Returns:
        The managed theme outputs directory, or the current working directory.
    """
    return outputs_dir(theme) if is_webapp_run() else Path.cwd()


def anchor_user_path(raw: str | Path, *, theme: str) -> Path:
    """Turn a user-supplied output path into an absolute one.

    A path typed into the web UI never passes through a shell, so nothing
    expands ``~`` and nothing resolves a relative path against anywhere
    meaningful — ``Path("~/Downloads/x.txt")`` is a *relative* path whose first
    component is a directory literally named ``~``, and writing to it silently
    creates that directory next to whatever the server happens to be running
    from. Every caller therefore anchors here first.

    The rules, in order:

    * ``~/x`` expands against the user's home directory.
    * An absolute path is left alone.
    * A relative path *with* a directory part (``Downloads/x.txt``) anchors to
      the home directory under the web UI, and to the current directory on the
      command line, where cwd is what a person typing it means.
    * A bare name (``x.txt``) anchors to the default output directory — the
      managed outputs tree under the web UI, cwd on the command line. This is
      the one form with no location in it at all, and the managed tree is what
      makes it show up in the UI's results list.

    Args:
        raw: Path exactly as the user supplied it.
        theme: Script theme slug, for the default outputs directory.

    Returns:
        An absolute path.
    """
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    if path.parent == Path("."):
        return _default_output_dir(theme) / path
    return relative_root() / path


def relative_root() -> Path:
    """Return what a relative path with a directory part is measured against.

    Args:
        None.

    Returns:
        The user's home directory for a web UI run, the current working
        directory otherwise.
    """
    return Path.home() if is_webapp_run() else Path.cwd()


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


def find_reported_outputs(
    lines: Iterable[str],
    root: Path | None = None,
    *,
    since: float | None = None,
) -> list[Path]:
    """Pick out the files a run wrote, by reading what it printed.

    Scripts announce their results inconsistently — ``print(out)`` in most,
    ``print(f"wrote {result}")`` in others, nothing at all in a few. Rather
    than a convention every one of them has to remember forever, this reads
    the output that already exists and keeps whatever turns out to be a real
    file the run is plausibly responsible for.

    Two candidates are tried per line: the whole line, which covers the bare
    ``print(path)`` case including paths containing spaces, and each
    whitespace-separated token, which covers a path embedded in a sentence.

    A file qualifies if it sits under *root*, or — when *since* is given — if it
    was last modified after the run began. The second test is what lets a result
    written to a directory the user named, such as ``~/Downloads``, still be
    reported, while a script merely echoing an input path is not credited with
    having written it: that file predates the run.

    Args:
        lines: Raw stdout lines from the run, unescaped.
        root: Directory results may live under; defaults to ``outputs_root()``.
        since: Epoch seconds the run started. When None, only *root* counts.

    Returns:
        Existing output files, in the order they were first mentioned.
    """
    root = (root or outputs_root()).resolve()
    found: dict[Path, None] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for candidate in (stripped, *stripped.split()):
            path = _written_by_run(candidate, root, since)
            if path is not None:
                found.setdefault(path, None)
                break

    return list(found)


def _written_by_run(candidate: str, root: Path, since: float | None) -> Path | None:
    """Return *candidate* as a resolved path if the run plausibly wrote it.

    Args:
        candidate: A string that may or may not be a path.
        root: Already-resolved directory a path may live under.
        since: Epoch seconds the run started, or None to require *root*.

    Returns:
        The resolved path, or None if it does not qualify.
    """
    text = candidate.strip().strip("'\"")
    if not text:
        return None
    try:
        path = Path(text).resolve()
        if not path.is_file():
            return None
        if path.is_relative_to(root):
            return path
        if since is not None and path.stat().st_mtime >= since:
            return path
    except OSError, ValueError:
        return None
    return None


def resolve_output(
    output: str | Path | None,
    *,
    theme: str,
    ext: str,
    makedirs: bool = True,
) -> Path:
    """Resolve user-provided ``--output`` to a concrete, collision-free path.

    The value is first made absolute by ``anchor_user_path``, which is what
    expands ``~`` and decides where a relative path is measured from. What is
    left is a shape question:

    * **Nothing** (``None``): default outputs dir + ``YYYYMMDD_HHmm.ext``.
    * **Existing directory**: that directory + ``YYYYMMDD_HHmm.ext``.
    * **Path with a file extension**: used as the output file.
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
        path = _default_output_dir(theme) / f"{stamp}{ext}"
    else:
        p = anchor_user_path(output, theme=theme)
        if p.is_dir():
            path = p / f"{stamp}{ext}"
        elif p.suffix:
            path = p
        else:
            path = p / f"{stamp}{ext}"

    if makedirs:
        path.parent.mkdir(parents=True, exist_ok=True)

    return deduplicate(path)


def names_a_file(output: str | Path | None) -> bool:
    """Report whether an ``--output`` value names a file rather than a directory.

    A suffix is the only signal available — the path need not exist yet.

    Args:
        output: Raw ``--output`` value, or ``None``.

    Returns:
        True when *output* carries a file extension.
    """
    return output is not None and Path(output).suffix != ""


def resolve_single_output(
    output: str | Path | None,
    *,
    theme: str,
    ext: str,
) -> Path | None:
    """Resolve ``--output`` only when it explicitly names one file.

    Scripts that may emit one *or* many files use ``resolve_output_dir``, which
    keeps only the directory part — correct for a batch, but it silently discards
    a filename the user typed. Such a script can call this first: a non-None
    result means "the user asked for exactly this file".

    Args:
        output: Raw ``--output`` value, or ``None``.
        theme: Script theme slug for the default outputs directory.
        ext: Fallback extension including the leading dot.

    Returns:
        A collision-free file path, or None when *output* is absent or names a
        directory.
    """
    if not names_a_file(output):
        return None
    return resolve_output(output, theme=theme, ext=ext)


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
        d = _default_output_dir(theme)
    else:
        p = anchor_user_path(output, theme=theme)
        if p.is_dir():
            d = p
        elif p.suffix:
            d = p.parent
        else:
            d = p

    if makedirs:
        d.mkdir(parents=True, exist_ok=True)
    return d
