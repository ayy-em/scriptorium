"""FastAPI web server for the Scriptorium script browser and runner."""

import argparse
import asyncio
import html
import json
import logging
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.categories import CATEGORY_EXTS, categorize
from core.config import UserConfig
from core.config import load as load_config
from core.config import save as save_config
from core.env import load_env
from core.paths import (
    FROZEN,
    drop_session_dir,
    has_ffmpeg,
    inputs_dir,
    logs_dir,
    outputs_root,
    read_version,
    static_dir,
    templates_dir,
)
from core.registry import (
    discover,
    discover_themes,
    scripts_for_file,
    theme_descriptions,
    theme_labels,
)
from webapp._badges import badges_for
from webapp._form import (
    accepts_directory,
    batch_mode_for,
    build_argv,
    field_specs_payload,
    fields_from_parser,
    file_input_for,
)
from webapp._icons import icon_for_category, icon_for_script

_CREATION_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

load_env()

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent

app = FastAPI(title="Scriptorium")
app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")
templates = Jinja2Templates(directory=str(templates_dir()))
templates.env.globals["is_frozen"] = FROZEN
templates.env.globals["has_ffmpeg"] = has_ffmpeg()
templates.env.globals["accepts_directory"] = accepts_directory
templates.env.globals["ffmpeg_install_hint"] = (
    "Install via Homebrew: brew install ffmpeg"
    if sys.platform == "darwin"
    else "Download ffmpeg from gyan.dev/ffmpeg/builds and add it to your PATH."
)


def accept_exts_for(mod) -> str:  # noqa: ANN001
    """Return an ``accept`` attribute value for a script's file input.

    Derived from the script's ``ACCEPTS`` categories, so the file picker filters
    to the types the script can actually handle and the dropzone can reject
    obviously wrong files before uploading them.

    Args:
        mod: The imported script module.

    Returns:
        Comma-separated extension list (e.g. ``".mp4,.mkv"``), or an empty
        string when the script declares no categories — meaning accept anything.
    """
    exts: set[str] = set()
    for category in getattr(mod, "ACCEPTS", set()):
        exts |= CATEGORY_EXTS.get(category, frozenset())
    return ",".join(sorted(exts))


def _read_git_hash() -> str:
    """Read the short git commit hash of the current HEAD.

    Returns:
        Short hash string, or "—" on any failure (including frozen mode).
    """
    if FROZEN:
        return "—"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            timeout=3,
            check=False,
            creationflags=_CREATION_FLAGS,
        )
        return result.stdout.strip() if result.returncode == 0 else "—"
    except Exception:
        return "—"


def _themes_search_json(themes: dict) -> str:
    """Serialise themes to a compact JSON string safe for inline script embedding.

    Each theme maps to a list of lowercase searchable strings (dot-key + title).

    Args:
        themes: Mapping of theme name → {script name → module}.

    Returns:
        JSON string with ``</`` escaped so it is safe inside a ``<script>`` tag.
    """
    data = {
        theme: [f"{theme}.{name} {mod.TITLE}".lower() for name, mod in scripts.items()]
        for theme, scripts in themes.items()
    }
    return json.dumps(data).replace("</", "<\\/")


_APP_VERSION = read_version()
_GIT_HASH = _read_git_hash()


@app.get("/")
async def index(request: Request):
    """List all available scripts grouped by theme."""
    themes = discover_themes()
    labels = theme_labels()
    descriptions = theme_descriptions()
    total_scripts = sum(len(s) for s in themes.values())
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "themes": themes,
            "all_themes": themes,
            "labels": labels,
            "descriptions": descriptions,
            "themes_data_json": _themes_search_json(themes),
            "total_scripts": total_scripts,
            "version": _APP_VERSION,
            "git_hash": _GIT_HASH,
        },
    )


@app.get("/scripts/{theme}/{script_name}")
async def script_detail(theme: str, script_name: str, request: Request):
    """Show a script's detail page with an auto-generated argument form."""
    key = f"{theme}.{script_name}"
    scripts = discover()
    if key not in scripts:
        raise HTTPException(status_code=404, detail=f"Script {key!r} not found")
    mod = scripts[key]
    parser = mod.get_parser() if hasattr(mod, "get_parser") else None
    field_specs = fields_from_parser(parser) if parser else []
    template_name = getattr(mod, "TEMPLATE", None) or "script.html"
    return templates.TemplateResponse(
        request,
        template_name,
        {
            "key": key,
            "key_path": key.replace(".", "/"),
            "theme": theme,
            "mod": mod,
            "field_specs": field_specs,
            "badges": badges_for(key, mod, field_specs),
            "accept_exts": accept_exts_for(mod),
            "all_themes": discover_themes(),
            "labels": theme_labels(),
            "version": _APP_VERSION,
            "git_hash": _GIT_HASH,
        },
    )


@app.get("/scripts/{theme}/{script_name}/run")
async def run_script(theme: str, script_name: str, request: Request) -> StreamingResponse:
    """Stream script output as Server-Sent Events."""
    key = f"{theme}.{script_name}"
    scripts = discover()
    if key not in scripts:
        raise HTTPException(status_code=404, detail=f"Script {key!r} not found")
    mod = scripts[key]
    parser = mod.get_parser() if hasattr(mod, "get_parser") else None
    field_specs = fields_from_parser(parser) if parser else []

    form_data = dict(request.query_params)
    argv = build_argv(form_data, field_specs)

    return StreamingResponse(
        _stream_script(key, argv),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/upload/{theme}")
async def upload_file(theme: str, file: UploadFile, subdir: str = "") -> JSONResponse:
    """Accept a file upload and save it to the theme's inputs directory.

    Args:
        theme: Script theme slug (e.g. "photo").
        file: Uploaded file.
        subdir: Optional batch subdirectory inside inputs/ to isolate
            uploads from different runs.
    """
    save_dir = inputs_dir(theme)
    if subdir:
        safe_name = Path(subdir).name
        if not safe_name or safe_name in (".", ".."):
            raise HTTPException(status_code=400, detail="Invalid subdir")
        save_dir = save_dir / safe_name
        save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / file.filename
    content = await file.read()
    save_path.write_bytes(content)
    return JSONResponse({"path": str(save_path), "filename": file.filename, "dir": str(save_dir)})


def _webview_window(request: Request):  # noqa: ANN201
    """Return the pywebview window backing this app, if there is one.

    Only the desktop wrapper sets this (see ``packaging/entrypoint.py``). In dev
    mode, Chromium ``--app`` mode, and the browser fallback it is absent, which
    is what gates the native folder picker.

    Args:
        request: The incoming request, used to reach ``app.state``.

    Returns:
        The pywebview window object, or ``None``.
    """
    return getattr(request.app.state, "webview_window", None)


@app.get("/api/settings")
async def get_settings(request: Request) -> JSONResponse:
    """Return current user settings plus which optional controls are usable."""
    cfg = load_config()
    return JSONResponse(
        {
            "theme": cfg.theme,
            "outputs_dir": cfg.outputs_dir,
            "close_behavior": cfg.close_behavior,
            "browse_supported": _webview_window(request) is not None,
        }
    )


@app.post("/api/browse-folder")
async def browse_folder(request: Request) -> JSONResponse:
    """Open a native folder picker and return the chosen directory.

    A browser cannot hand back an absolute directory path, so this only works
    under the pywebview desktop wrapper. Everywhere else the UI disables the
    Browse button and the user types a path instead.

    Returns:
        JSON with the selected ``path``, or an empty string if the user
        cancelled the dialog.

    Raises:
        HTTPException: 501 when no native window is available to host a dialog.
    """
    window = _webview_window(request)
    if window is None:
        raise HTTPException(status_code=501, detail="Folder picker requires the desktop app")

    def _pick() -> str:
        import webview  # noqa: PLC0415

        result = window.create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return ""
        return str(result[0]) if isinstance(result, (list, tuple)) else str(result)

    try:
        # create_file_dialog blocks until the user answers; keep the event loop free.
        path = await asyncio.to_thread(_pick)
    except Exception:
        logger.debug("Folder dialog failed", exc_info=True)
        raise HTTPException(status_code=500, detail="Folder picker failed") from None

    return JSONResponse({"path": path})


@app.post("/api/open-logs")
async def open_logs() -> JSONResponse:
    """Open the logs directory in the OS file explorer.

    Offered by the splash screen's failure state, which is reachable when the
    UI scripts never initialise and the rest of the app is unusable.

    Returns:
        JSON acknowledgement.
    """
    _open_in_file_manager(logs_dir())
    return JSONResponse({"ok": True})


@app.post("/api/settings")
async def post_settings(request: Request) -> JSONResponse:
    """Persist user settings to config.json."""
    body = await request.json()
    cfg = UserConfig(
        theme=body.get("theme", "light"),
        outputs_dir=body.get("outputs_dir", ""),
        close_behavior=body.get("close_behavior", "close"),
    )
    save_config(cfg)
    return JSONResponse({"ok": True})


def _open_in_file_manager(folder: Path) -> None:
    """Reveal a directory in the platform's file manager.

    Args:
        folder: Directory to open.
    """
    if sys.platform == "win32":
        subprocess.Popen(["explorer", str(folder)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(folder)])
    else:
        subprocess.Popen(["xdg-open", str(folder)])


@app.post("/api/open-outputs")
async def open_outputs() -> JSONResponse:
    """Open the outputs root folder in the OS file explorer.

    Opens the root rather than a per-theme subdirectory, so the user sees
    every theme's results at once.

    Returns:
        JSON acknowledgement.
    """
    _open_in_file_manager(outputs_root())
    return JSONResponse({"ok": True})


@app.post("/api/quit")
async def quit_server(request: Request) -> JSONResponse:
    """Signal the uvicorn server to shut down (frozen mode only).

    Returns:
        JSON acknowledgement, or 403 if not running in frozen mode.
    """
    if not FROZEN:
        raise HTTPException(status_code=403, detail="Quit is only available in the desktop app")
    uv_server = getattr(request.app.state, "uv_server", None)
    if uv_server is None:
        raise HTTPException(status_code=503, detail="Server reference not available")
    logger.info("Quit requested via API — shutting down")
    uv_server.should_exit = True
    return JSONResponse({"ok": True})


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of integers for comparison.

    Args:
        version: Dotted version string like ``"0.3.0"``.

    Returns:
        Tuple of integers, e.g. ``(0, 3, 0)``.
    """
    return tuple(int(x) for x in version.split(".") if x.isdigit())


_GITHUB_RELEASES_URL = "https://api.github.com/repos/ayy-em/scriptorium/releases/latest"


@app.get("/api/update-check")
async def update_check() -> JSONResponse:
    """Check GitHub Releases for a newer version.

    Returns:
        JSON with ``update_available``, ``current``, ``latest``, and ``url`` fields.
    """
    import httpx  # noqa: PLC0415

    current = _APP_VERSION
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                _GITHUB_RELEASES_URL,
                timeout=5.0,
                headers={"Accept": "application/vnd.github+json"},
            )
            resp.raise_for_status()
            data = resp.json()
            latest = data["tag_name"].lstrip("v")
            return JSONResponse(
                {
                    "current": current,
                    "latest": latest,
                    "update_available": _parse_version(latest) > _parse_version(current),
                    "url": data.get("html_url", ""),
                }
            )
    except Exception:
        logger.debug("Update check failed", exc_info=True)
        return JSONResponse({"current": current, "update_available": False})


def _has_extra_fields(mod) -> bool:
    """Check whether a script has form fields beyond the file input."""
    if not hasattr(mod, "get_parser"):
        return False
    specs = fields_from_parser(mod.get_parser())
    return any(not (s.is_positional and s.widget in ("file", "file-multi")) for s in specs)


def _script_summary(key: str, mod) -> dict:
    """Build the chooser payload describing one script.

    Args:
        key: Dotted script key such as ``"av.trim"``.
        mod: The imported script module.

    Returns:
        Dict with display metadata, batch classification, whether the script
        renders a custom template, and whether its input accepts a directory.
    """
    specs = fields_from_parser(mod.get_parser()) if hasattr(mod, "get_parser") else []
    file_input = file_input_for(specs)
    theme, name = key.split(".", 1)
    return {
        "key": key,
        "theme": theme,
        "name": name,
        "title": mod.TITLE,
        "description": mod.DESCRIPTION,
        "has_extra_fields": _has_extra_fields(mod),
        "has_template": bool(getattr(mod, "TEMPLATE", None)),
        "batch_mode": batch_mode_for(specs),
        "accepts_directory": accepts_directory(file_input),
        "file_dest": file_input.dest if file_input else None,
        "icon": icon_for_script(key),
    }


def _new_drop_session() -> tuple[str, Path]:
    """Create an isolated directory for one drop or paste.

    Each drop gets its own subdirectory so that directory-native scripts such
    as ``av.join`` never pick up leftovers from an earlier drop.

    Returns:
        Tuple of (session id, created directory path).
    """
    session_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    return session_id, drop_session_dir(session_id)


@app.post("/api/drop-upload")
async def drop_upload(files: list[UploadFile]) -> JSONResponse:
    """Accept one or more dropped files and return the scripts that match them.

    All files in a batch must share a single category; mixed batches are
    rejected so that the chooser never has to intersect incompatible script
    sets. Files are written into a per-drop session directory.

    Args:
        files: Uploaded files from the browser, all of the same category.

    Returns:
        JSON describing the session, the batch, and every matching script.

    Raises:
        HTTPException: 400 if the batch is empty, contains an unrecognised file
            type, or mixes categories.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    names = [Path(f.filename or "").name for f in files]
    if any(not n for n in names):
        raise HTTPException(status_code=400, detail="A file was uploaded without a name")

    categories = {categorize(n) for n in names}
    if None in categories:
        unknown = sorted({Path(n).suffix.lower() or n for n in names if categorize(n) is None})
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {', '.join(unknown)}")
    if len(categories) > 1:
        listed = ", ".join(sorted(c for c in categories if c))
        raise HTTPException(
            status_code=400,
            detail=f"All files must be the same type — got {listed}",
        )

    category = categories.pop()
    session_id, session_dir = _new_drop_session()

    saved = []
    for upload, name in zip(files, names, strict=True):
        content = await upload.read()
        (session_dir / name).write_bytes(content)
        saved.append({"filename": name, "path": str(session_dir / name), "size": len(content)})

    scripts_data = [_script_summary(key, mod) for key, mod in scripts_for_file(names[0])]

    return JSONResponse(
        {
            "session_id": session_id,
            "dir": str(session_dir),
            "category": category,
            "category_icon": icon_for_category(category),
            "count": len(saved),
            "total_size": sum(f["size"] for f in saved),
            "files": saved,
            "scripts": scripts_data,
        }
    )


@app.get("/api/script-fields/{theme}/{script_name}")
async def script_fields(theme: str, script_name: str) -> JSONResponse:
    """Return form field specs for a script, excluding file inputs."""
    key = f"{theme}.{script_name}"
    all_scripts = discover()
    if key not in all_scripts:
        raise HTTPException(status_code=404, detail=f"Script {key!r} not found")

    mod = all_scripts[key]
    if not hasattr(mod, "get_parser"):
        return JSONResponse({"fields": []})

    specs = fields_from_parser(mod.get_parser())
    filtered = [s for s in specs if not (s.is_positional and s.widget in ("file", "file-multi"))]

    return JSONResponse({"fields": field_specs_payload(filtered)})


def _cli_prefix() -> list[str]:
    """Return the command tokens that invoke Scriptorium on this install.

    Returns:
        ``["scriptorium"]`` for the packaged app, otherwise the dev invocation.
    """
    return ["scriptorium"] if FROZEN else ["uv", "run", "main.py"]


def _quote_command(tokens: list[str]) -> str:
    """Join argv tokens into a string the user's own shell will accept.

    Windows and POSIX disagree about quoting, and this string exists to be
    copy-pasted, so the platform convention matters.

    Args:
        tokens: Command tokens, already in argv order.

    Returns:
        A single copy-pasteable command line.
    """
    if sys.platform == "win32":
        return subprocess.list2cmdline(tokens)
    return shlex.join(tokens)


@app.get("/api/preview-command/{theme}/{script_name}")
async def preview_command(theme: str, script_name: str, request: Request) -> JSONResponse:
    """Render the CLI command equivalent to the current form state.

    Shares ``build_argv`` with the run endpoint, so the preview cannot drift
    from what actually executes.

    Args:
        theme: Script theme slug.
        script_name: Script module name.
        request: Request whose query params carry the current form values.

    Returns:
        JSON with the assembled ``command`` string.

    Raises:
        HTTPException: 404 if the script key is unknown.
    """
    key = f"{theme}.{script_name}"
    scripts = discover()
    if key not in scripts:
        raise HTTPException(status_code=404, detail=f"Script {key!r} not found")

    mod = scripts[key]
    parser = mod.get_parser() if hasattr(mod, "get_parser") else None
    field_specs = fields_from_parser(parser) if parser else []
    argv = build_argv(dict(request.query_params), field_specs)

    return JSONResponse({"command": _quote_command([*_cli_prefix(), key, *argv])})


async def _stream_script(key: str, argv: list[str]):
    """Run a script as a subprocess and yield its output as SSE events.

    Yields stdout lines first, then stderr lines. Each line is HTML-escaped.
    A final 'done' event signals the client to close the connection and
    includes a JSON payload with the exit code and elapsed time.

    Args:
        key: Script key (e.g. "av.convert").
        argv: Pre-built list of CLI arguments to pass after the script key.

    Yields:
        SSE-formatted byte strings.
    """
    import time  # noqa: PLC0415

    if FROZEN:
        cmd = [sys.executable, "--run-script", key, *argv]
        cwd = None
    else:
        cmd = [sys.executable, str(_REPO_ROOT / "main.py"), key, *argv]
        cwd = str(_REPO_ROOT)

    t0 = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )

    async for line in proc.stdout:  # type: ignore[union-attr]
        text = html.escape(line.decode(errors="replace").rstrip())
        yield f"data: {text}\n\n".encode()

    async for line in proc.stderr:  # type: ignore[union-attr]
        text = html.escape(line.decode(errors="replace").rstrip())
        yield f"data: <span class='stderr'>{text}</span>\n\n".encode()

    await proc.wait()
    rc = proc.returncode
    elapsed = round(time.monotonic() - t0, 1)
    css = "exit-ok" if rc == 0 else "exit-err"
    yield f"data: <span class='{css}'>exit {rc}</span>\n\n".encode()
    done_payload = json.dumps({"exit_code": rc, "elapsed": elapsed})
    yield f"event: done\ndata: {done_payload}\n\n".encode()


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the web server CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description="Serve a local browser UI for browsing and running scripts.",
        prog="uv run main.py web.serve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    return parser


def run() -> None:
    """Start the uvicorn server."""
    import uvicorn  # noqa: PLC0415

    args = get_parser().parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
