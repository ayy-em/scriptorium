"""CLI entry point for the Scriptorium web UI server."""

TITLE = "Web UI server"
DESCRIPTION = "Serve a local browser UI for browsing and running scripts."


def get_parser():
    """Return the argument parser for this script.

    Returns:
        Configured ArgumentParser instance.
    """
    from webapp.app import get_parser as _get_parser  # noqa: PLC0415

    return _get_parser()


def run() -> None:
    """CLI entrypoint. Start the uvicorn server."""
    from webapp.app import run as _run  # noqa: PLC0415

    _run()
