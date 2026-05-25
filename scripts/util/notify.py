"""Telegram bot notifier — pings a chat when a long-running script finishes."""

import argparse
import os
import sys

import httpx

from core.argparse import ScriptoriumParser

TITLE = "Send a Telegram notification"
DESCRIPTION = "Post a message to a Telegram chat. Used standalone or as a runner hook for long jobs."

_API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT_SECONDS = 10.0


def _credentials() -> tuple[str, str] | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return None
    return token, chat_id


def send(message: str) -> bool:
    """Send a Telegram message. Returns True on HTTP 2xx, False otherwise.

    All errors (missing credentials, network failure, non-2xx response) are
    swallowed and reduced to a False return value so callers can ignore them.
    """
    creds = _credentials()
    if creds is None:
        return False
    token, chat_id = creds
    try:
        response = httpx.post(
            _API_TEMPLATE.format(token=token),
            data={"chat_id": chat_id, "text": message},
            timeout=_TIMEOUT_SECONDS,
        )
        return response.is_success
    except Exception:
        return False


def format_run_message(label: str, status: str, duration_s: float) -> str:
    """Render a one-line summary suitable for a Telegram notification."""
    emoji = "✅" if status == "done" else "❌"
    return f"{emoji} {label}: {status} in {duration_s:.3f}s"


_EXAMPLES = """
examples:
  uv run main.py util.notify --message "build finished"
  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... uv run main.py util.notify -m "hi"
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py util.notify",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--message",
        "-m",
        required=True,
        help="message body to send",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Send the message; exit non-zero on failure."""
    args = get_parser().parse_args()
    ok = send(args.message)
    if not ok:
        print("notify: failed to send (missing credentials or network error)", file=sys.stderr)
    sys.exit(0 if ok else 1)
