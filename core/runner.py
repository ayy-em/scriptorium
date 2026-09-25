"""Script runner with timing middleware for CLI and programmatic dispatch."""

from collections.abc import Callable
from datetime import UTC, datetime
import json
import os
import sys
import time
from typing import Any

from core.paths import logs_dir
from core.registry import discover

_RUNS_LOG_NAME = "runs.jsonl"
_NOTIFY_ENV_VAR = "SCRIPTORIUM_NOTIFY"


def _log_run(label: str, duration_s: float, status: str) -> None:
    """Append a single run record to logs/runs.jsonl. Never raises."""
    try:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "label": label,
            "duration_s": round(duration_s, 3),
            "status": status,
        }
        path = logs_dir() / _RUNS_LOG_NAME
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass


def _should_notify(duration_s: float) -> bool:
    """Decide whether a finished run earns a Telegram message.

    ``SCRIPTORIUM_NOTIFY`` in the environment forces a message for every run,
    which is what a terminal user wrapping one long command wants. Otherwise
    the settings modal decides: notifications on, and the run at least as long
    as the configured threshold, so a two-second run does not ping a phone.

    Args:
        duration_s: How long the run took.

    Returns:
        True when a message should be sent.
    """
    if os.environ.get(_NOTIFY_ENV_VAR, "").strip() in ("1", "true", "yes"):
        return True
    from core.config import load as load_config  # noqa: PLC0415

    cfg = load_config()
    return cfg.notify_telegram and duration_s >= cfg.notify_min_seconds


def _maybe_notify(label: str, duration_s: float, status: str) -> None:
    """Send a Telegram notification when the run qualifies. Never raises."""
    try:
        if not _should_notify(duration_s):
            return
    except Exception:
        return
    try:
        from scripts.util.notify import format_run_message, send  # noqa: PLC0415

        send(format_run_message(label, status, duration_s))
    except Exception:
        pass


def _timed[T](label: str, fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    stamp = datetime.now().strftime("%d-%m-%y %H:%M")
    print(f"[{label}] started at {stamp}", file=sys.stderr)
    t0 = time.perf_counter()
    try:
        result = fn(*args, **kwargs)
    except SystemExit as exc:
        elapsed = time.perf_counter() - t0
        status = "failed" if exc.code not in (0, None) else "done"
        print(f"[{label}] {status} in {elapsed:.3f}s", file=sys.stderr)
        _log_run(label, elapsed, status)
        _maybe_notify(label, elapsed, status)
        raise
    except Exception:
        elapsed = time.perf_counter() - t0
        print(f"[{label}] failed after {elapsed:.3f}s", file=sys.stderr)
        _log_run(label, elapsed, "failed")
        _maybe_notify(label, elapsed, "failed")
        raise
    elapsed = time.perf_counter() - t0
    print(f"[{label}] done in {elapsed:.3f}s", file=sys.stderr)
    _log_run(label, elapsed, "done")
    _maybe_notify(label, elapsed, "done")
    return result  # type: ignore[return-value]


def run(script_key: str) -> None:
    """Dispatch a script by key, applying timing middleware."""
    scripts = discover()
    if script_key not in scripts:
        available = ", ".join(sorted(scripts)) or "none"
        raise KeyError(f"Unknown script {script_key!r}. Available: {available}")
    sys.argv.pop(1)  # consumed by dispatcher; script's argparse sees only its own args
    _timed(script_key, scripts[script_key].run)


def run_fn[T](fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """Programmatic entry point. Same middleware as CLI run() but takes a typed callable."""
    label = fn.__module__.removeprefix("scripts.") + "::" + fn.__qualname__
    return _timed(label, fn, *args, **kwargs)
