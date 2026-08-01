"""Run history persistence backed by ~/scriptorium/history.json.

Records what ran, with which arguments, and how it ended. Deliberately kept
free of asyncio and of any live process state — that lives in
``webapp._runs`` — so a record stays a plain value that can be stored, replayed
and reasoned about on its own.
"""

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path

from core.paths import _user_data_dir

logger = logging.getLogger(__name__)

_HISTORY_PATH = _user_data_dir() / "history.json"

# Newest-first cap. High enough to be a useful record, low enough that the file
# stays small and the history page needs no pagination.
MAX_ENTRIES = 200

SUCCESS = "success"
ERROR = "error"
CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunRecord:
    """One completed script run.

    Attributes:
        run_id: Opaque identifier, unique per run.
        key: Dotted script key such as ``"av.filmstrip"``.
        argv: CLI arguments the script was invoked with, after the key.
        params: Original form values, kept so a re-run can prefill the form.
            ``argv`` is what actually ran; ``params`` is what the user typed.
        status: One of ``"success"``, ``"error"`` or ``"cancelled"``.
        exit_code: Process exit code, or None if it never produced one.
        started_at: ISO 8601 local timestamp of when the run began.
        elapsed: Wall-clock seconds the run took.
        batch_id: Groups the runs of one per-file fan-out. Empty for an
            ordinary single invocation. A batch is N invocations over a file
            set, so it needs no record type of its own — just a shared id.
        outputs: Files the run was detected to have written, as strings.
            Best-effort — derived from what the script printed, so a script
            that prints nothing records nothing. See
            ``core.outputs.find_reported_outputs``.
    """

    run_id: str
    key: str
    status: str
    started_at: str
    elapsed: float
    exit_code: int | None = None
    argv: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)
    batch_id: str = ""

    @property
    def theme(self) -> str:
        """Return the theme half of the script key."""
        return self.key.split(".", 1)[0]

    @property
    def script_name(self) -> str:
        """Return the script half of the script key."""
        return self.key.split(".", 1)[-1]


def _from_raw(raw: dict) -> RunRecord | None:
    """Build a RunRecord from a decoded JSON object, or None if unusable.

    A single malformed entry should not cost the user their whole history, so
    bad rows are skipped rather than raised.

    Args:
        raw: One decoded entry from the history file.

    Returns:
        The record, or None when required fields are missing or mistyped.
    """
    try:
        return RunRecord(
            run_id=str(raw["run_id"]),
            key=str(raw["key"]),
            status=str(raw["status"]),
            started_at=str(raw["started_at"]),
            elapsed=float(raw["elapsed"]),
            exit_code=None if raw.get("exit_code") is None else int(raw["exit_code"]),
            argv=[str(a) for a in raw.get("argv", [])],
            params={str(k): str(v) for k, v in (raw.get("params") or {}).items()},
            outputs=[str(o) for o in raw.get("outputs", [])],
            batch_id=str(raw.get("batch_id", "")),
        )
    except KeyError, TypeError, ValueError:
        return None


def load() -> list[RunRecord]:
    """Read the run history, newest first.

    Returns:
        Stored records. Empty when the file is missing, unreadable or corrupt —
        a broken history file is an inconvenience, not a reason to fail.
    """
    if not _HISTORY_PATH.exists():
        return []
    try:
        raw = json.loads(_HISTORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read %s, starting with empty history", _HISTORY_PATH)
        return []
    if not isinstance(raw, list):
        logger.warning("%s is not a list, starting with empty history", _HISTORY_PATH)
        return []
    return [record for record in (_from_raw(r) for r in raw if isinstance(r, dict)) if record is not None]


def save(records: list[RunRecord]) -> None:
    """Write the history file, truncated to MAX_ENTRIES.

    Args:
        records: Records to persist, newest first.
    """
    _HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _HISTORY_PATH.write_text(
        json.dumps([asdict(r) for r in records[:MAX_ENTRIES]], indent=2),
        encoding="utf-8",
    )


def append(record: RunRecord) -> None:
    """Add a record to the front of the history, dropping the oldest past the cap.

    Args:
        record: The completed run to store.
    """
    save([record, *load()])


def get(run_id: str) -> RunRecord | None:
    """Look up a single record.

    Args:
        run_id: Identifier to find.

    Returns:
        The matching record, or None.
    """
    return next((r for r in load() if r.run_id == run_id), None)


def clear() -> None:
    """Delete all history."""
    save([])


def history_path() -> Path:
    """Return the path to the history file.

    Returns:
        Absolute path to ``history.json``.
    """
    return _HISTORY_PATH
