"""FastAPI web server for the Scriptorium script browser and runner."""

import argparse
import asyncio
import html
from pathlib import Path
import sys

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates

from core.registry import discover, discover_themes
from scripts.web._form import build_argv, fields_from_parser

TITLE = "Web UI server"
DESCRIPTION = "Serve a local browser UI for browsing and running scripts."

_REPO_ROOT = Path(__file__).parent.parent.parent
_TEMPLATES_DIR = Path(__file__).parent / "templates"

app = FastAPI(title="Scriptorium")
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


@app.get("/")
async def index(request: Request):
    """List all available scripts grouped by theme."""
    return templates.TemplateResponse(request, "index.html", {"themes": discover_themes()})


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
        {"key": key, "key_path": key.replace(".", "/"), "mod": mod, "field_specs": field_specs},
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
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py web.serve",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    return parser


def run() -> None:
    """CLI entrypoint. Start the uvicorn server."""
    import uvicorn  # noqa: PLC0415

    args = get_parser().parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
