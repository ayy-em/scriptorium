"""Entry point for the frozen Scriptorium app (.app on macOS, .exe on Windows).

Handles two modes:
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (no args)                      Start the web server in a background thread
                                 and open a native webview window (pywebview).
                                 Falls back to the default browser if the
                                 native window cannot be initialised.
"""

import socket
import sys
import threading
import time


def _find_free_port(start: int = 8000, end: int = 8100) -> int:
    """Find the first available TCP port in the given range.

    Args:
        start: First port to try.
        end: One past the last port to try.

    Returns:
        An available port, or *start* if none found.
    """
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _run_server(uv_server) -> None:  # noqa: ANN001
    """Run the uvicorn server (target for the background thread).

    Args:
        uv_server: A ``uvicorn.Server`` instance.
    """
    uv_server.run()


def _wait_for_server(uv_server, timeout: float = 10.0) -> bool:  # noqa: ANN001
    """Block until the uvicorn server signals it has started.

    Args:
        uv_server: A ``uvicorn.Server`` instance.
        timeout: Maximum seconds to wait.

    Returns:
        True if the server started within *timeout*, False otherwise.
    """
    deadline = time.monotonic() + timeout
    while not uv_server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    return uv_server.started


def _browser_fallback(url: str, uv_server, logger) -> None:  # noqa: ANN001
    """Open the app in the default browser and block until the user dismisses a dialog.

    On Windows (non-console .exe) a native message-box is shown.  On other
    platforms a terminal ``input()`` prompt is used instead.

    Args:
        url: The local URL the server is listening on.
        uv_server: A ``uvicorn.Server`` instance to shut down on dismissal.
        logger: Logger for diagnostic messages.
    """
    import webbrowser  # noqa: PLC0415

    webbrowser.open(url)
    logger.info("Opened browser fallback at %s", url)

    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415

        ctypes.windll.user32.MessageBoxW(
            0,
            f"Scriptorium is running at {url}\n\nClick OK to stop the server and exit.",
            "Scriptorium",
            0x00000040,  # MB_ICONINFORMATION
        )
    else:
        try:
            input("Press Enter to stop the server...\n")
        except (EOFError, KeyboardInterrupt):
            pass

    uv_server.should_exit = True


def main() -> None:
    """Dispatch to script runner or desktop UI."""
    if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from main import main as cli_main  # noqa: PLC0415

        cli_main()
        return

    import logging  # noqa: PLC0415

    import uvicorn  # noqa: PLC0415

    from webapp.app import app  # noqa: PLC0415

    logging.basicConfig(level=logging.WARNING)
    logger = logging.getLogger("scriptorium.entrypoint")

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uv_server = uvicorn.Server(config)

    server_thread = threading.Thread(target=_run_server, args=(uv_server,), daemon=True)
    server_thread.start()

    if not _wait_for_server(uv_server):
        logger.error("Server failed to start within timeout")
        sys.exit(1)

    try:
        import webview  # noqa: PLC0415
    except ImportError:
        webview = None

    if webview is not None:
        try:
            window = webview.create_window("Scriptorium", url, width=1200, height=800)
            window.events.closed += lambda: setattr(uv_server, "should_exit", True)
            webview.start()
            uv_server.should_exit = True
            server_thread.join(timeout=5.0)
        except Exception:
            logger.exception("pywebview failed, falling back to browser")
            _browser_fallback(url, uv_server, logger)
    else:
        _browser_fallback(url, uv_server, logger)


if __name__ == "__main__":
    main()
