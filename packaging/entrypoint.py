"""Entry point for the frozen Scriptorium .app bundle.

Handles two modes:
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (no args)                      Start the web server in a background thread
                                 and host the UI in a native WKWebView window
                                 so the .app owns its own dock icon and has
                                 no browser chrome.
"""

import socket
import sys
import threading


def _find_free_port(start: int = 8000, end: int = 8100) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return start


def _run_server(port: int) -> None:
    import uvicorn  # noqa: PLC0415

    from webapp.app import app  # noqa: PLC0415

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def main() -> None:
    """Dispatch to script runner or desktop UI."""
    if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from main import main as cli_main  # noqa: PLC0415

        cli_main()
        return

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"Starting Scriptorium at {url}")

    server = threading.Thread(target=_run_server, args=(port,), daemon=True)
    server.start()

    try:
        import webview  # noqa: PLC0415
    except ImportError:
        import webbrowser  # noqa: PLC0415

        webbrowser.open(url)
        server.join()
        return

    webview.create_window("Scriptorium", url, width=1200, height=800)
    webview.start()


if __name__ == "__main__":
    main()
