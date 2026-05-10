import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar

from core.registry import discover

T = TypeVar("T")


def _timed(label: str, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except SystemExit as exc:
        elapsed = time.perf_counter() - t0
        status = "failed" if exc.code not in (0, None) else "done"
        print(f"[{label}] {status} in {elapsed:.3f}s", file=sys.stderr)
        raise
    except Exception:
        print(f"[{label}] failed after {time.perf_counter() - t0:.3f}s", file=sys.stderr)
        raise
    print(f"[{label}] done in {time.perf_counter() - t0:.3f}s", file=sys.stderr)
    return result  # type: ignore[return-value]


def run(script_key: str) -> None:
    scripts = discover()
    if script_key not in scripts:
        available = ", ".join(sorted(scripts)) or "none"
        raise KeyError(f"Unknown script {script_key!r}. Available: {available}")
    sys.argv.pop(1)  # consumed by dispatcher; script's argparse sees only its own args
    _timed(script_key, scripts[script_key].run)


def run_fn(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Programmatic entry point. Same middleware as CLI run() but takes a typed callable."""
    label = fn.__module__.removeprefix("scripts.") + "::" + fn.__qualname__
    return _timed(label, fn, *args, **kwargs)
