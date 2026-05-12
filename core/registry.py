"""Auto-discovery of script modules that expose TITLE, DESCRIPTION, and run()."""

import importlib
import pkgutil
from types import ModuleType

import scripts as _scripts_pkg

_REQUIRED = ("TITLE", "DESCRIPTION", "run")


def discover() -> dict[str, ModuleType]:
    """Return {theme.name: module} for every script that exposes TITLE, DESCRIPTION, and run()."""
    result: dict[str, ModuleType] = {}
    for theme in pkgutil.iter_modules(_scripts_pkg.__path__):
        if theme.name.startswith("_"):
            continue
        theme_mod = importlib.import_module(f"scripts.{theme.name}")
        for script in pkgutil.iter_modules(theme_mod.__path__):
            if script.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module(f"scripts.{theme.name}.{script.name}")
            except ImportError:
                continue
            if all(hasattr(mod, attr) for attr in _REQUIRED):
                result[f"{theme.name}.{script.name}"] = mod
    return result


def theme_labels() -> dict[str, str]:
    """Return {theme_key: display_label} for each discovered theme.

    Reads the LABEL module attribute; falls back to title-cased key if absent.

    Returns:
        Mapping of theme key to human-readable label string.
    """
    result: dict[str, str] = {}
    for theme in pkgutil.iter_modules(_scripts_pkg.__path__):
        if theme.name.startswith("_"):
            continue
        mod = importlib.import_module(f"scripts.{theme.name}")
        result[theme.name] = getattr(mod, "LABEL", theme.name.replace("_", " ").title())
    return result


def discover_themes() -> dict[str, dict[str, ModuleType]]:
    """Return {theme: {script_name: module}} for all discovered scripts.

    Returns:
        Nested dict grouping script modules by their theme name.
    """
    grouped: dict[str, dict[str, ModuleType]] = {}
    for key, mod in discover().items():
        theme, script = key.split(".", 1)
        grouped.setdefault(theme, {})[script] = mod
    return {theme: scripts for theme, scripts in grouped.items() if scripts}
