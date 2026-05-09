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
            mod = importlib.import_module(f"scripts.{theme.name}.{script.name}")
            if all(hasattr(mod, attr) for attr in _REQUIRED):
                result[f"{theme.name}.{script.name}"] = mod
    return result
