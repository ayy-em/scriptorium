"""Entry point for the frozen Scriptorium app (.app on macOS, .exe on Windows).

Handles three modes:
  <theme.script> [args...]       Run a script directly from the terminal (CLI
                                 mode — only active when scriptorium.exe is the
                                 console-mode build and stdout is attached).
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (no args / windowed build)     Start the web server in a background thread
                                 and open a desktop window.  Tries three tiers:
                                 1. pywebview native window
                                 2. Edge/Chrome --app mode (chromeless)
                                 3. Default browser fallback (quit via UI)
"""

import socket
import sys
import threading
import time


def _find_free_port(start: int = 57200, end: int = 57300) -> int:
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
    """Locate a Chromium-based browser on the system.

    On Windows, searches the registry, well-known filesystem paths, and PATH.
    On macOS, searches /Applications and common install locations.
    On Linux, searches common binary names on PATH.

    Returns:
        A ``(name, exe_path)`` tuple, or ``None`` if none found.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415

    if sys.platform == "win32":
        return _find_chromium_windows()

    if sys.platform == "darwin":
        candidates = [
            (
                "Google Chrome",
                [
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                ],
            ),
            (
                "Microsoft Edge",
                [
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    os.path.expanduser("~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                ],
            ),
            (
                "Chromium",
                [
                    "/Applications/Chromium.app/Contents/MacOS/Chromium",
                ],
            ),
        ]
    else:
        candidates = [
            ("Google Chrome", []),
            ("Chromium", []),
            ("Microsoft Edge", []),
        ]
        which_names = ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "microsoft-edge"]
        for wn in which_names:
            found = shutil.which(wn)
            if found:
                name = "Google Chrome" if "chrome" in wn else ("Chromium" if "chromium" in wn else "Microsoft Edge")
                return (name, found)

    for name, known_paths in candidates:
        for path in known_paths:
            if os.path.isfile(path):
                return (name, path)

    for exe_name in ["google-chrome", "chromium-browser", "chromium"]:
        found = shutil.which(exe_name)
        if found:
            return (exe_name.replace("-", " ").title(), found)

    return None


def _find_chromium_windows() -> tuple[str, str] | None:
    """Locate Edge or Chrome on Windows via registry and filesystem.

    Returns:
        A ``(name, exe_path)`` tuple, or ``None`` if neither is found.
    """
    import os  # noqa: PLC0415
    import shutil  # noqa: PLC0415
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


def _chromium_app_window(url: str, uv_server, logger) -> None:  # noqa: ANN001
    """Open the app in a chromeless Chromium ``--app`` window.

    Blocks until the user closes the window, then signals the server to stop.

    Args:
        url: The local URL the server is listening on.
        uv_server: A ``uvicorn.Server`` instance to shut down on exit.
        logger: Logger for diagnostic messages.

    Raises:
        RuntimeError: If no Chromium-based browser is found.
    """
    from pathlib import Path  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

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


def _browser_fallback(url: str, server_thread: threading.Thread, logger) -> None:  # noqa: ANN001
    """Open the app in the default browser and block until the server stops.

    The user can stop the server via the Quit button in the web UI, which
    calls the ``/api/quit`` endpoint.

    Args:
        url: The local URL the server is listening on.
        server_thread: The background thread running the server.
        logger: Logger for diagnostic messages.
    """
    import webbrowser  # noqa: PLC0415

    webbrowser.open(url)
    logger.info("Opened browser fallback at %s — quit via the UI", url)

    try:
        server_thread.join()
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down")


def _load_tray_icon():  # noqa: ANN201
    """Load the app icon for the system tray from the static icons directory.

    Returns:
        A PIL ``Image`` instance, or ``None`` if loading fails.
    """
    try:
        import PIL.Image  # noqa: PLC0415

        from core.paths import static_dir  # noqa: PLC0415

        icon_path = static_dir() / "icons" / "icon-night.png"
        if icon_path.exists():
            img = PIL.Image.open(icon_path).convert("RGBA").resize((64, 64), PIL.Image.LANCZOS)
            return img
    except Exception:
        pass
    return None


def _create_tray_icon(window):  # noqa: ANN001, ANN201
    """Create and start a system tray icon with Show/Quit menu items.

    Args:
        window: The pywebview window to show/hide.

    Returns:
        Running ``pystray.Icon`` instance, or ``None`` if pystray is unavailable.
    """
    try:
        import pystray  # noqa: PLC0415

        icon_image = _load_tray_icon()
        if icon_image is None:
            return None

        def on_show(icon, item):  # noqa: ANN001
            window.show()

        def on_quit(icon, item):  # noqa: ANN001
            icon.stop()
            import os  # noqa: PLC0415

            os._exit(0)  # noqa: SLF001

        menu = pystray.Menu(
            pystray.MenuItem("Show Scriptorium", on_show, default=True),
            pystray.MenuItem("Quit", on_quit),
        )
        tray = pystray.Icon("Scriptorium", icon_image, "Scriptorium", menu)
        t = threading.Thread(target=tray.run, daemon=True)
        t.start()
        return tray
    except Exception:
        return None


def _make_closing_handler(window, tray_icon):  # noqa: ANN001, ANN201
    """Return a ``window.events.closing`` handler that respects close_behavior.

    Args:
        window: The pywebview window to show/hide.
        tray_icon: Running ``pystray.Icon`` instance, or ``None``.

    Returns:
        A no-arg function that returns ``False`` to cancel close when
        ``close_behavior`` is ``"tray"``, or ``None`` to allow it.
    """

    def _handler():  # noqa: ANN202
        from core.config import load as load_config  # noqa: PLC0415

        cfg = load_config()
        if cfg.close_behavior == "tray" and tray_icon is not None:
            window.hide()
            return False
        return None

    return _handler


def _run_cli() -> None:
    """Invoke the CLI dispatcher from main.py."""
    from main import main as cli_main  # noqa: PLC0415

    cli_main()


def _start_gui(logger, url: str, uv_server, server_thread: threading.Thread, app=None) -> None:  # noqa: ANN001
    """Try to open a GUI window, attempting three tiers in order.

    Tier 1: pywebview native window (preferred on desktop installs).
    Tier 2: Chromium --app mode (chromeless, cross-platform).
    Tier 3: Default browser fallback (user quits via the in-app Quit button).

    Args:
        logger: Logger for diagnostic messages.
        url: The local URL the server is listening on.
        uv_server: A ``uvicorn.Server`` instance.
        server_thread: The background thread running the server.
        app: The FastAPI app, so the native window can be published on
            ``app.state`` for endpoints that need to raise OS dialogs. Only
            tier 1 has a window; the other tiers leave it unset, which is how
            the UI knows to disable the folder picker.
    """
    try:
        import webview  # noqa: PLC0415
    except ImportError:
        webview = None
        logger.info("pywebview not available, skipping native window")

    if webview is not None:
        try:
            import os  # noqa: PLC0415

            _patch_webview2_external_drop()
            window = webview.create_window("Scriptorium", url, width=1200, height=800)
            if app is not None:
                app.state.webview_window = window

            tray_icon = _create_tray_icon(window)
            window.events.closing += _make_closing_handler(window, tray_icon)

            webview.start()

            if tray_icon is not None:
                tray_icon.stop()
            uv_server.should_exit = True
            server_thread.join(timeout=5.0)
            os._exit(0)  # noqa: SLF001
        except Exception:
            uv_server.should_exit = False
            if app is not None:
                app.state.webview_window = None
            logger.exception("pywebview failed — trying Chromium app mode")

    try:
        _chromium_app_window(url, uv_server, logger)
        server_thread.join(timeout=5.0)
        return
    except Exception:
        logger.exception("Chromium app mode failed — falling back to browser")

    _browser_fallback(url, server_thread, logger)
    server_thread.join(timeout=5.0)


def _patch_webview2_external_drop() -> None:
    """Force AllowExternalDrop=True on the WebView2 WinForms control.

    WebView2 WinForms SDK 1.0.1340+ exposes AllowExternalDrop on the wrapper
    control. pywebview never sets it, and some runtime versions silently default
    it to False, which blocks OS-level file drag-and-drop from reaching the
    HTML5 drag events used by the drop overlay.
    """
    try:
        from webview.platforms import edgechromium as _ec  # noqa: PLC0415

        _orig_init = _ec.EdgeChrome.__init__

        def _patched_init(self, form, window, cache_dir):  # type: ignore[override]
            _orig_init(self, form, window, cache_dir)
            try:
                self.webview.AllowExternalDrop = True
            except Exception:
                pass

        _ec.EdgeChrome.__init__ = _patched_init
    except Exception:
        pass


def main() -> None:
    """Dispatch to CLI or start the desktop GUI.

    Console-mode build (scriptorium.exe, console=True): always routes to CLI.
    Windowed build (ScriptoriumApp.exe, console=False): starts the GUI server.
    Both builds support --run-script for internal subprocess dispatch.
    """
    _console_mode = sys.stdout is not None  # check BEFORE patching streams
    _patch_missing_streams()

    if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        _run_cli()
        return

    if _console_mode:
        _run_cli()
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

    app.state.uv_server = uv_server

    server_thread = threading.Thread(target=_run_server, args=(uv_server,), daemon=True)
    server_thread.start()

    if not _wait_for_server(uv_server):
        logger.error("Server failed to start within timeout")
        sys.exit(1)

    _start_gui(logger, url, uv_server, server_thread, app)


if __name__ == "__main__":
    main()
