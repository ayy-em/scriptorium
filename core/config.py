"""User settings persistence backed by ~/scriptorium/config.json."""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path

from core.paths import _user_data_dir

logger = logging.getLogger(__name__)

_CONFIG_PATH = _user_data_dir() / "config.json"


@dataclass
class UserConfig:
    """Persistent user settings.

    Attributes:
        theme: Color scheme — ``"light"`` or ``"dark"``.
        outputs_dir: Custom root directory for script outputs, or empty string
            for the default.
    """

    theme: str = "light"
    outputs_dir: str = ""


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
        )
    except Exception:
        logger.warning("Failed to read %s, using defaults", _CONFIG_PATH)
        return UserConfig()


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
