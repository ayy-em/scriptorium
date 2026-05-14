"""Entry point for the frozen Scriptorium app (.app on macOS, .exe on Windows).

Handles two modes:
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (no args)                      Start the web server in a background thread
                                 and open a desktop window.  Tries three tiers:
                                 1. pywebview native window
                                 2. Edge/Chrome --app mode (chromeless)
                                 3. Default browser + MessageBox fallback
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


def _patch_missing_streams() -> None:
    """Replace None stdio streams with usable handles.

    In a frozen Windows app without a console, sys.stdout/sys.stderr are None.
    Uvicorn's formatter calls .isatty() on them, which crashes.

    When frozen on Windows, stderr goes to a log file so that diagnostic
    messages (e.g. pywebview init failures) are preserved for debugging.
    """
    import os  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    devnull = open(os.devnull, "w")  # noqa: SIM115, PTH123

    if sys.stdout is None:
        sys.stdout = devnull

    if sys.stderr is None:
        if getattr(sys, "frozen", False) and sys.platform == "win32":
            log_dir = Path.home() / "scriptorium"
            log_dir.mkdir(parents=True, exist_ok=True)
            sys.stderr = open(log_dir / "scriptorium.log", "a")  # noqa: SIM115, PTH123
        else:
            sys.stderr = devnull


def _find_chromium_browser() -> tuple[str, str] | None:
    """Locate Edge or Chrome on the system.

    Searches the Windows registry, well-known filesystem paths, and PATH.

    Returns:
        A ``(name, exe_path)`` tuple, or ``None`` if neither is found.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    if sys.platform != "win32":
        return None

    import winreg  # noqa: PLC0415

    candidates = [
        (
            "Edge",
            "msedge.exe",
            [
                os.path.join(
                    os.environ.get("ProgramFiles(x86)", ""),
                    "Microsoft",
                    "Edge",
                    "Application",
                    "msedge.exe",
                ),
                os.path.join(
                    os.environ.get("ProgramFiles", ""),
                    "Microsoft",
                    "Edge",
                    "Application",
                    "msedge.exe",
                ),
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    "Microsoft",
                    "Edge",
                    "Application",
                    "msedge.exe",
                ),
            ],
        ),
        (
            "Chrome",
            "chrome.exe",
            [
                os.path.join(
                    os.environ.get("ProgramFiles", ""),
                    "Google",
                    "Chrome",
                    "Application",
                    "chrome.exe",
                ),
                os.path.join(
                    os.environ.get("ProgramFiles(x86)", ""),
                    "Google",
                    "Chrome",
                    "Application",
                    "chrome.exe",
                ),
                os.path.join(
                    os.environ.get("LOCALAPPDATA", ""),
                    "Google",
                    "Chrome",
                    "Application",
                    "chrome.exe",
                ),
            ],
        ),
    ]

    for name, exe_name, known_paths in candidates:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(
                    hive,
                    rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
                ) as key:
                    path, _ = winreg.QueryValueEx(key, "")
                    if os.path.isfile(path):
                        return (name, path)
            except OSError:
                continue

        for path in known_paths:
            if path and os.path.isfile(path):
                return (name, path)

        found = shutil.which(exe_name)
        if found:
            return (name, found)

    return None


def _edge_app_window(url: str, uv_server, logger) -> None:  # noqa: ANN001
    """Open the app in a chromeless Edge/Chrome ``--app`` window.

    Blocks until the user closes the window, then signals the server to stop.

    Args:
        url: The local URL the server is listening on.
        uv_server: A ``uvicorn.Server`` instance to shut down on exit.
        logger: Logger for diagnostic messages.

    Raises:
        RuntimeError: If no Chromium-based browser is found.
    """
    import subprocess  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    browser = _find_chromium_browser()
    if browser is None:
        raise RuntimeError("No Chromium-based browser found")

    name, exe_path = browser
    profile_dir = str(Path.home() / "scriptorium" / ".browser-profile")

    cmd = [
        exe_path,
        f"--app={url}",
        "--window-size=1200,800",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--disable-extensions",
    ]

    logger.info("Launching %s in app mode: %s", name, exe_path)
    proc = subprocess.Popen(cmd)  # noqa: S603

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()

    uv_server.should_exit = True


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
            f"Scriptorium is running at {url}\n\n"
            "A standalone window could not be opened.\n"
            "The app has been opened in your default browser instead.\n\n"
            "Click OK to stop the server and exit.",
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
    _patch_missing_streams()

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

    # Tier 1: pywebview native window
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        webview = None
        logger.info("pywebview not available, skipping native window")

    if webview is not None:
        try:
            window = webview.create_window("Scriptorium", url, width=1200, height=800)
            webview.start()
            uv_server.should_exit = True
            server_thread.join(timeout=5.0)
            return
        except Exception:
            uv_server.should_exit = False
            logger.exception("pywebview failed — trying Edge app mode")

    # Tier 2: Edge/Chrome --app mode
    if sys.platform == "win32":
        try:
            _edge_app_window(url, uv_server, logger)
            server_thread.join(timeout=5.0)
            return
        except Exception:
            logger.exception("Edge app mode failed — falling back to browser")

    # Tier 3: plain browser fallback
    _browser_fallback(url, uv_server, logger)
    server_thread.join(timeout=5.0)


if __name__ == "__main__":
    main()
