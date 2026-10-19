"""Centralized path resolution for frozen (PyInstaller) and development modes."""

from datetime import datetime
from pathlib import Path
import shutil
import sys
import tomllib

from core.invocation import is_webapp_run

FROZEN = getattr(sys, "frozen", False)


def _bundle_dir() -> Path:
    """Root of the PyInstaller bundle, or the repo root in development."""
    if FROZEN:
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).parent.parent


def _user_data_dir() -> Path:
    """Return ~/scriptorium/ — user-facing data directory for the packaged app."""
    return Path.home() / "scriptorium"


def templates_dir() -> Path:
    """Return the Jinja2 templates directory."""
    return _bundle_dir() / "webapp" / "templates"


def static_dir() -> Path:
    """Return the static assets directory."""
    return _bundle_dir() / "webapp" / "static"


def assets_dir() -> Path:
    """Return the shared assets directory (fonts, images used across themes)."""
    return _bundle_dir() / "assets"


def inputs_dir(theme: str) -> Path:  # noqa: ARG001
    """Return the shared inputs directory, creating it if needed.

    Theme argument is preserved for API compatibility but ignored: every script
    reads from the same root inputs directory.
    """
    d = _user_data_dir() / "inputs" if FROZEN else _bundle_dir() / "inputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_input(source: Path, theme: str) -> Path:
    """Resolve a user-supplied input path for whoever supplied it.

    ``~`` is expanded first: nothing typed into the web UI passes through a
    shell, so an unexpanded tilde would be read as a directory of that literal
    name sitting next to the server.

    A bare filename is the ambiguous case. From the web UI it names a file
    staged in ``inputs/``; from a terminal it names a file in the current
    directory, the way every other command-line tool behaves. A relative path
    *with* a directory part is measured against the home directory under the web
    UI and against the current directory on the command line, matching
    ``core.outputs.anchor_user_path``. Absolute paths are returned untouched.

    ``./name`` is *not* a way to force the cwd: ``Path`` normalises the leading
    ``./`` away at construction, so it arrives here identical to ``name``. That
    costs nothing in practice — the web UI passes absolute paths (the upload
    endpoint returns one), so its bare-filename branch only ever serves a human
    who put a file in ``inputs/`` and typed its name.

    Finally, a staged path that no longer exists is followed into
    ``inputs/processed/``. A successful run archives its own input, so the path
    the caller is holding — a form field, a history record, a command in shell
    history — stops existing the moment it is used once. Following it is what
    lets the same file be run twice in a row, which is the normal way of
    finding the right ``--crf`` or the right cut.

    Args:
        source: Path exactly as the caller supplied it.
        theme: Script theme slug, for the inputs directory lookup.

    Returns:
        The path to actually read from.
    """
    from core.outputs import relative_root  # noqa: PLC0415

    source = source.expanduser()
    if source.is_absolute():
        resolved = source
    elif source.parent != Path("."):
        resolved = relative_root() / source
    elif is_webapp_run():
        resolved = inputs_dir(theme) / source.name
    else:
        resolved = source

    # Every branch is offered the archive, but ``archived_copy`` only follows a
    # path that lands inside the staging area. A bare name on the command line
    # means a file in the current directory, so it is followed only when that
    # directory is itself inside ``inputs/`` — never from somewhere unrelated.
    archived = archived_copy(theme, resolved)
    if archived is None:
        return resolved
    print(f"{resolved.name} was archived by an earlier run; reading {archived}")
    return archived


def drop_session_dir(session_id: str) -> Path:
    """Return an isolated directory for one drag-drop or paste session.

    Lives at ``inputs/drop/<session_id>/`` so that directory-native scripts run
    against exactly the files just dropped, without picking up unrelated files
    sitting in the shared inputs root.

    Args:
        session_id: Filesystem-safe identifier for this drop.

    Returns:
        The created session directory.
    """
    d = inputs_dir("drop") / "drop" / session_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def past_inputs_dir(theme: str) -> Path:  # noqa: ARG001
    """Return the processed-inputs archive directory, creating it if needed.

    Lives at ``inputs/processed/`` so users can see archived files alongside
    their unprocessed ones. Theme argument preserved for API compatibility.
    """
    d = inputs_dir(theme) / "processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def move_to_past_inputs(theme: str, source: Path) -> Path | None:
    """Move a processed input file to ``inputs/processed/``.

    This is the only sanctioned way to archive an input, and the guard is the
    reason: a file is moved **only** when it lives inside the shared inputs
    root. Point a script at ``~/Movies/holiday.mp4`` and it is read and left
    exactly where it was; stage a file in ``inputs/`` and it is filed away once
    it has been used. Scripts that rolled their own ``processed/`` directory
    created one next to whatever the user pointed at, which made pointing a
    script at a real media library a destructive act.

    Files already inside ``processed/`` are skipped, so re-running against the
    archive does not shuffle it.

    **The archived file keeps its own name**, and on a name collision it is the
    *older* copy that is moved aside, not the new one. That ordering is what
    makes ``archived_copy`` able to answer "where did the file I was just
    using go?" with a plain path lookup: ``processed/<name>`` is always the
    most recently archived file of that name. The other way round — which is
    how this worked at first — a second ``report.csv`` archived under a
    timestamped name and left the first sitting at ``processed/report.csv``,
    so looking the name up found the wrong month's data.

    Args:
        theme: Script theme slug, for the inputs directory lookup.
        source: File the run has finished with.

    Returns:
        The destination path, or ``None`` when the source was skipped (outside
        the inputs root, already archived, not a file) or the move failed.
        Callers ignore the return value: failing to tidy up is never a reason
        to fail a run that already produced its output.
    """
    if not _is_archivable(theme, source):
        return None

    dest = past_inputs_dir(theme).resolve() / source.name
    if dest.exists() and not _displace(dest):
        return None
    try:
        shutil.move(str(source), str(dest))
    except OSError:
        return None
    return dest


def _is_archivable(theme: str, source: Path) -> bool:
    """Report whether *source* is a staged input this app may file away.

    Args:
        theme: Script theme slug, for the inputs directory lookup.
        source: Candidate file.

    Returns:
        True for an existing file inside the inputs tree but not already
        inside ``processed/``.
    """
    if not source.is_file():
        return False
    try:
        source_resolved = source.resolve()
        inputs_root = inputs_dir(theme).resolve()
        past_root = past_inputs_dir(theme).resolve()
    except OSError:
        return False
    if not source_resolved.is_relative_to(inputs_root):
        return False
    return not source_resolved.is_relative_to(past_root)


def _displace(archived: Path) -> bool:
    """Move an already-archived file aside so a newer one can take its name.

    The timestamp comes from the displaced file's own modification time rather
    than from now, so the suffix says when that copy is from instead of when it
    happened to be bumped.

    Args:
        archived: Existing file inside ``processed/`` whose name is wanted.

    Returns:
        True when the name is free afterwards, False when it could not be
        vacated — in which case the caller leaves the archive alone rather
        than overwriting a file it cannot preserve.
    """
    from core.outputs import deduplicate  # noqa: PLC0415

    try:
        stamp = datetime.fromtimestamp(archived.stat().st_mtime).strftime("%Y%m%dT%H%M%S")
        aside = deduplicate(archived.with_stem(f"{archived.stem}_{stamp}"))
        archived.rename(aside)
    except OSError, FileExistsError:
        return False
    return True


def archived_copy(theme: str, candidate: Path) -> Path | None:
    """Return where *candidate* was archived to, if that is where it now lives.

    Archiving an input after a successful run means the path the caller is
    holding stops existing. That is correct housekeeping and a miserable
    experience: pressing Run twice, or re-running from history, fails on a file
    that is sitting right there in ``processed/``. This answers "the thing I
    was pointed at has moved — where to?" so callers can follow it.

    Only paths inside the shared inputs tree are followed. A missing
    ``~/Movies/holiday.mp4`` stays missing rather than silently resolving to an
    unrelated ``inputs/processed/holiday.mp4`` that happens to share a name.

    Args:
        theme: Script theme slug, for the inputs directory lookup.
        candidate: The path that was expected to exist.

    Returns:
        The archived file, or None when *candidate* still exists, sits outside
        the inputs tree, or has no archived counterpart.
    """
    if candidate.exists():
        return None
    try:
        inputs_root = inputs_dir(theme).resolve()
        if not candidate.resolve().is_relative_to(inputs_root):
            return None
        archived = past_inputs_dir(theme) / candidate.name
    except OSError:
        return None
    return archived if archived.is_file() else None


def logs_dir() -> Path:
    """Return the directory for runtime logs, creating it if needed."""
    if FROZEN:
        d = _user_data_dir() / "logs"
    else:
        d = _bundle_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_root() -> Path:
    """Return the root outputs directory, creating it if needed.

    Unlike outputs_dir(), no theme subdirectory is appended. Used by the
    "open outputs folder" button, which reveals every theme's results at once
    rather than guessing at one.

    Returns:
        The outputs root — the user's configured directory if set, otherwise
        the default location for this install.
    """
    from core.config import load as _load_config  # noqa: PLC0415

    custom = _load_config().outputs_dir
    if custom:
        d = Path(custom)
    elif FROZEN:
        d = _user_data_dir() / "outputs"
    else:
        d = _bundle_dir() / "outputs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def outputs_dir(theme: str) -> Path:
    """Return the outputs directory for a theme, creating it if needed.

    If the user has set a custom outputs directory in settings, it is used
    as the root (with a theme subdirectory). Otherwise the default location
    is used.
    """
    d = outputs_root() / theme
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_version() -> str:
    """Read the project version, with frozen-mode fallback."""
    try:
        with open(_bundle_dir() / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "—"


def read_build_sha() -> str:
    """Read the commit hash a frozen build was made from.

    ``packaging/build_sha.py`` writes the file while the spec runs, since the
    bundle itself carries no repository to ask. Absent in development, where
    the webapp asks git directly.

    Returns:
        The short hash, or an empty string when the file is missing or blank.
    """
    try:
        return (_bundle_dir() / "build_sha.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""
