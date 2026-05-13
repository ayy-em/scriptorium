"""Entry point for the frozen Scriptorium .app bundle.

Handles two modes:
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (no args)                      Start the web server and open the browser.
"""

import socket
import sys
import webbrowser


def _find_free_port(start: int = 8000, end: int = 8100) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def main() -> None:
    """Dispatch to script runner or web server."""
    if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from main import main as cli_main  # noqa: PLC0415

        cli_main()
        return

    import uvicorn  # noqa: PLC0415

    from webapp.app import app  # noqa: PLC0415

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Scriptorium at {url}")
    webbrowser.open(url)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
