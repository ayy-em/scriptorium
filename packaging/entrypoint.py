"""Entry point for the frozen Scriptorium app (.app on macOS, .exe on Windows).

Handles three modes:
  <theme.script> [args...]       Run a script directly from the terminal (CLI
                                 mode — any explicit argument, or a bare launch
                                 from an interactive tty).
  --run-script <key> [args...]   Run a script via the CLI dispatcher (used
                                 internally by the webapp subprocess runner).
  (windowed launch, no args)     Start the web server in a background thread
                                 and open a desktop window.  Tries three tiers:
                                 1. pywebview native window
                                 2. Edge/Chrome --app mode (chromeless)
                                 3. Default browser fallback (quit via UI)
"""

import socket
import sys
import threading
import time

_MACOS = sys.platform == "darwin"


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

    Blocks until the user closes the window. When ``close_behavior`` is ``"tray"``
    and a tray icon could be created, the window is reopened on demand from the
    tray instead of the app exiting — otherwise this fallback tier would ignore
    the setting entirely, which is what happens when pywebview is unavailable.

    Args:
        url: The local URL the server is listening on.
        uv_server: A ``uvicorn.Server`` instance to shut down on exit.
        logger: Logger for diagnostic messages.

    Raises:
        RuntimeError: If no Chromium-based browser is found.
    """
    from pathlib import Path  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import threading as _threading  # noqa: PLC0415

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

    reopen = _threading.Event()
    quit_requested = _threading.Event()

    def _open() -> subprocess.Popen:
        logger.info("Launching %s in app mode: %s", name, exe_path)
        return subprocess.Popen(cmd)  # noqa: S603

    # This tier has no GUI main loop of its own — it just waits on a browser
    # process — so on macOS there is nothing to service an NSStatusItem. A
    # background pystray thread would abort the process instead (see
    # _create_tray_icon_for), so the setting is skipped rather than fatal.
    if _MACOS:
        tray_icon = None
        logger.info("Chromium tier on macOS: no tray icon (no NSApplication loop to service it)")
    else:
        tray_icon = _create_tray_icon_for(reopen.set, quit_requested.set)

    if tray_icon is None:
        logger.info("No tray icon available; window close will exit the app")

    # A failure here falls through to the browser tier, which has no tray of its
    # own — so the icon has to go with the window rather than outliving it.
    try:
        proc = _open()
        while True:
            try:
                proc.wait()
            except KeyboardInterrupt:
                proc.terminate()
                break

            if quit_requested.is_set() or tray_icon is None or not _close_to_tray():
                break

            # Window closed but the user wants us resident: idle until the tray
            # asks for the window back, or for the app to quit.
            logger.info("Window closed — staying in the tray")
            reopen.clear()
            while not reopen.wait(timeout=0.5):
                if quit_requested.is_set():
                    break
            if quit_requested.is_set():
                break
            proc = _open()
    finally:
        _stop_tray(tray_icon)

    uv_server.should_exit = True


def _close_to_tray() -> bool:
    """Report whether the user asked the close button to minimise to tray.

    Returns:
        True when ``close_behavior`` is ``"tray"``.
    """
    from core.config import load as load_config  # noqa: PLC0415

    return load_config().close_behavior == "tray"


def _create_tray_icon_for(on_show, on_quit, *, detached: bool = False):  # noqa: ANN001, ANN201
    """Create a tray icon wired to arbitrary show/quit callbacks.

    The pywebview tier can show and hide its own window, but the Chromium tier
    has to relaunch a process instead, so the actions are injected rather than
    hard-coded.

    Args:
        on_show: Called when the user picks "Show Scriptorium".
        on_quit: Called when the user picks "Quit".
        detached: Attach the icon to a main loop the caller is about to enter,
            rather than driving it from a background thread. Required on macOS,
            where ``Icon.run`` calls ``-[NSApplication run]`` — AppKit aborts
            the whole process with SIGTRAP ("NSUpdateCycleInitialize() is
            called off the main thread") if that happens anywhere but the main
            thread, and a signal is not an exception, so nothing can catch it.

    Returns:
        A live ``pystray.Icon`` instance, or ``None`` if unavailable.
    """
    try:
        import pystray  # noqa: PLC0415

        icon_image = _load_tray_icon()
        if icon_image is None:
            return None

        menu = pystray.Menu(
            pystray.MenuItem("Show Scriptorium", lambda icon, item: on_show(), default=True),
            pystray.MenuItem("Quit", lambda icon, item: on_quit()),
        )
        tray = pystray.Icon("Scriptorium", icon_image, "Scriptorium", menu)
        if detached:
            # Returns immediately; the caller's main loop services the icon.
            tray.run_detached()
        else:
            threading.Thread(target=tray.run, daemon=True).start()
        return tray
    except Exception:
        return None


def _stop_tray(tray_icon) -> None:  # noqa: ANN001
    """Tear down a tray icon, tolerating one that never finished starting.

    ``Icon.run`` is on a background thread, so a caller unwinding from an error
    can reach here before the icon's own loop is ready and ``stop()`` raises.
    That must not mask the original failure or block the next window tier.

    Args:
        tray_icon: A ``pystray.Icon`` instance, or ``None``.
    """
    if tray_icon is None:
        return
    try:
        tray_icon.stop()
    except Exception:
        pass


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
    """Load the app logo for the system tray.

    pystray needs a raster, so this reads a PNG logo rather than the vector
    ``logo.svg`` the UI uses. ``logo-64.png`` is already cut to the tray size;
    the 512px master is only a fallback and gets downsampled on every launch.

    Returns:
        A PIL ``Image`` instance, or ``None`` if loading fails.
    """
    try:
        import PIL.Image  # noqa: PLC0415

        from core.paths import static_dir  # noqa: PLC0415

        static = static_dir()
        for name in ("logo-64.png", "logo.png"):
            icon_path = static / name
            if icon_path.exists():
                img = PIL.Image.open(icon_path).convert("RGBA")
                if img.size != (64, 64):
                    img = img.resize((64, 64), PIL.Image.LANCZOS)
                return img
    except Exception:
        pass
    return None


def _create_tray_icon(window):  # noqa: ANN001, ANN201
    """Create a tray icon that shows and hides a pywebview window.

    On macOS the icon is attached detached-style to the shared NSApplication
    that ``webview.start()`` is about to run — both pystray and pywebview use
    ``NSApplication.sharedApplication()``, so that one loop drives both.

    Args:
        window: The pywebview window to show/hide.

    Returns:
        A live ``pystray.Icon`` instance, or ``None`` if pystray is unavailable.
    """

    def _quit() -> None:
        import os  # noqa: PLC0415

        os._exit(0)  # noqa: SLF001

    return _create_tray_icon_for(window.show, _quit, detached=_MACOS)


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
        if tray_icon is not None and _close_to_tray():
            window.hide()
            return False
        return None

    return _handler


def _cli_args() -> list[str]:
    """Return the user-supplied argv, minus anything the OS injected.

    macOS LaunchServices can append a ``-psn_0_<pid>`` process-serial argument
    when opening a bundle, which must not be mistaken for a script key.

    Returns:
        The argument list the user actually passed.
    """
    return [a for a in sys.argv[1:] if not a.startswith("-psn_")]


def _wants_cli() -> bool:
    """Report whether this invocation should run the CLI instead of the GUI.

    Called before the stdio streams are patched, because the answer depends on
    what the OS handed us.

    Two things mean "CLI": explicit arguments (a script key, ``--help``), or a
    bare invocation from an interactive terminal, where listing the scripts is
    the useful response.

    A tty check rather than ``sys.stdout is not None``: only a Windows windowed
    build gets None streams. macOS and Linux windowed launches inherit valid
    stdio from launchd/the desktop session — pointed at /dev/null or the system
    log, but not None — so the None check sent every Finder launch into the CLI,
    which printed the script list to nowhere and exited. That is a dock bounce
    and no window.

    Returns:
        True to run the CLI, False to start the desktop GUI.
    """
    if _cli_args():
        return True

    try:
        return sys.stdout is not None and sys.stdout.isatty()
    except AttributeError, ValueError, OSError:
        # Closed or exotic stream: no terminal to talk to, so treat as windowed.
        return False


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

    # Bound before the try so the handler can tear the icon down no matter how
    # far tier 1 got.
    tray_icon = None

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

            _stop_tray(tray_icon)
            uv_server.should_exit = True
            server_thread.join(timeout=5.0)
            os._exit(0)  # noqa: SLF001
        except Exception:
            # By the time webview.start() fails the tier-1 icon is already live
            # on its own thread, and its menu points at a window that never
            # opened. Left up, it sits alongside the icon the Chromium tier is
            # about to create — two Scriptorium icons, the first one broken.
            _stop_tray(tray_icon)
            tray_icon = None
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

    Terminal invocation — with a script key, or bare from a tty — routes to the
    CLI. A windowed launch (Finder, Start menu, .desktop file) starts the GUI
    server. Every build supports --run-script for internal subprocess dispatch.
    """
    _cli = _wants_cli()  # decide BEFORE patching streams
    _patch_missing_streams()

    if len(sys.argv) > 1 and sys.argv[1] == "--run-script":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        _run_cli()
        return

    if _cli:
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
