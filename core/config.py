"""User settings persistence backed by ~/scriptorium/config.json."""

from dataclasses import asdict, dataclass, field
import json
import logging
from pathlib import Path

from core.paths import _user_data_dir

logger = logging.getLogger(__name__)

_CONFIG_PATH = _user_data_dir() / "config.json"

SORT_ORDERS = ("az", "za", "count")
DEFAULT_SORT_ORDER = "az"


@dataclass
class UserConfig:
    """Persistent user settings.

    Attributes:
        theme: Color scheme — ``"light"`` or ``"dark"``.
        outputs_dir: Custom root directory for script outputs, or empty string
            for the default.
        close_behavior: What the window close button does — ``"close"`` exits
            the app, ``"tray"`` hides it to the system tray.
        favourites: Script keys the user has starred, e.g. ``"av.trim"``.
            Server-side rather than in ``localStorage`` because the packaged
            app has three launch tiers and they do not share browser storage.
        sort_order: Category ordering — one of ``SORT_ORDERS``.
    """

    theme: str = "light"
    outputs_dir: str = ""
    close_behavior: str = "close"
    favourites: list[str] = field(default_factory=list)
    sort_order: str = DEFAULT_SORT_ORDER


def load() -> UserConfig:
    """Load settings from disk, returning defaults if the file is missing or corrupt.

    Returns:
        A populated ``UserConfig`` instance.
    """
    if not _CONFIG_PATH.exists():
        return UserConfig()
    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        return UserConfig(
            theme=raw.get("theme", "light"),
            outputs_dir=raw.get("outputs_dir", ""),
            close_behavior=raw.get("close_behavior", "close"),
            favourites=clean_favourites(raw.get("favourites")),
            sort_order=clean_sort_order(raw.get("sort_order")),
        )
    except Exception:
        logger.warning("Failed to read %s, using defaults", _CONFIG_PATH)
        return UserConfig()


def clean_favourites(raw: object) -> list[str]:
    """Coerce a stored favourites value into a list of script keys.

    The file is user-editable, and a malformed entry here would otherwise reach
    the template as-is.

    Args:
        raw: Whatever was under ``favourites`` in the config file.

    Returns:
        Deduplicated script keys, order preserved; empty if unusable.
    """
    if not isinstance(raw, list):
        return []
    seen: dict[str, None] = {}
    for item in raw:
        if isinstance(item, str) and item:
            seen.setdefault(item, None)
    return list(seen)


def clean_sort_order(raw: object) -> str:
    """Return *raw* if it names a known sort order, else the default.

    Args:
        raw: Whatever was under ``sort_order`` in the config file.

    Returns:
        A valid sort order id.
    """
    return raw if raw in SORT_ORDERS else DEFAULT_SORT_ORDER


def save(cfg: UserConfig) -> None:
    """Write settings to disk.

    Args:
        cfg: The settings to persist.
    """
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), indent=2),
        encoding="utf-8",
    )


def config_path() -> Path:
    """Return the path to the config file.

    Returns:
        Absolute path to ``config.json``.
    """
    return _CONFIG_PATH
