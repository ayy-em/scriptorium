"""FastAPI web server for the Scriptorium script browser and runner."""

import argparse
import asyncio
import html
import json
import logging
from pathlib import Path
import subprocess
import sys

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.config import UserConfig
from core.config import load as load_config
from core.config import save as save_config
from core.paths import FROZEN, has_ffmpeg, inputs_dir, read_version, static_dir, templates_dir
from core.registry import discover, discover_themes, theme_descriptions, theme_labels
from webapp._form import build_argv, fields_from_parser

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent

app = FastAPI(title="Scriptorium")
app.mount("/static", StaticFiles(directory=str(static_dir())), name="static")
templates = Jinja2Templates(directory=str(templates_dir()))
templates.env.globals["is_frozen"] = FROZEN
templates.env.globals["has_ffmpeg"] = has_ffmpeg()
templates.env.globals["ffmpeg_install_hint"] = (
    "Install via Homebrew: brew install ffmpeg"
    if sys.platform == "darwin"
    else "Download ffmpeg from gyan.dev/ffmpeg/builds and add it to your PATH."
)


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
    return templates.TemplateResponse(
        request,
        "script.html",
        {
            "key": key,
            "key_path": key.replace(".", "/"),
            "mod": mod,
            "field_specs": field_specs,
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
async def upload_file(theme: str, file: UploadFile) -> JSONResponse:
    """Accept a file upload and save it to the theme's inputs directory."""
    save_dir = inputs_dir(theme)
    save_path = save_dir / file.filename
    content = await file.read()
    save_path.write_bytes(content)
    return JSONResponse({"path": str(save_path), "filename": file.filename})


@app.get("/api/settings")
async def get_settings() -> JSONResponse:
    """Return current user settings."""
    cfg = load_config()
    return JSONResponse({"theme": cfg.theme, "outputs_dir": cfg.outputs_dir})


@app.post("/api/settings")
async def post_settings(request: Request) -> JSONResponse:
    """Persist user settings to config.json."""
    body = await request.json()
    cfg = UserConfig(
        theme=body.get("theme", "light"),
        outputs_dir=body.get("outputs_dir", ""),
    )
    save_config(cfg)
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
