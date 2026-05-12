"""FastAPI web server for the Scriptorium script browser and runner."""

import argparse
import asyncio
import html
import json
from pathlib import Path
import subprocess
import sys
import tomllib

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.registry import discover, discover_themes, theme_labels
from webapp._form import build_argv, fields_from_parser

_REPO_ROOT = Path(__file__).parent.parent
_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Scriptorium")
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _read_version() -> str:
    """Read the project version from pyproject.toml.

    Returns:
        Version string, or "—" on any failure.
    """
    try:
        with open(_REPO_ROOT / "pyproject.toml", "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except Exception:
        return "—"


def _read_git_hash() -> str:
    """Read the short git commit hash of the current HEAD.

    Returns:
        Short hash string, or "—" on any failure.
    """
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


_APP_VERSION = _read_version()
_GIT_HASH = _read_git_hash()


@app.get("/")
async def index(request: Request):
    """List all available scripts grouped by theme."""
    themes = discover_themes()
    labels = theme_labels()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "themes": themes,
            "all_themes": themes,
            "labels": labels,
            "themes_data_json": _themes_search_json(themes),
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


async def _stream_script(key: str, argv: list[str]):
    """Run a script as a subprocess and yield its output as SSE events.

    Yields stdout lines first, then stderr lines. Each line is HTML-escaped.
    A final 'done' event signals the client to close the connection.

    Args:
        key: Script key (e.g. "av.convert").
        argv: Pre-built list of CLI arguments to pass after the script key.

    Yields:
        SSE-formatted byte strings.
    """
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(_REPO_ROOT / "main.py"),
        key,
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(_REPO_ROOT),
    )

    async for line in proc.stdout:  # type: ignore[union-attr]
        text = html.escape(line.decode(errors="replace").rstrip())
        yield f"data: {text}\n\n".encode()

    async for line in proc.stderr:  # type: ignore[union-attr]
        text = html.escape(line.decode(errors="replace").rstrip())
        yield f"data: <span class='stderr'>{text}</span>\n\n".encode()

    await proc.wait()
    rc = proc.returncode
    css = "exit-ok" if rc == 0 else "exit-err"
    yield f"data: <span class='{css}'>exit {rc}</span>\n\n".encode()
    yield b"event: done\ndata: \n\n"


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
