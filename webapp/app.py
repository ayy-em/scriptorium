"""FastAPI web server for the Scriptorium script browser and runner."""

import argparse
import asyncio
import html
import json
import logging
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import urllib.request
import uuid

from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core import capabilities, history
from core.categories import CATEGORY_EXTS, categorize
from core.config import UserConfig, clean_favourites, clean_notify_min_seconds, clean_sort_order
from core.config import load as load_config
from core.config import save as save_config
from core.env import load_env, set_env_value
from core.invocation import webapp_spawn_env
from core.outputs import find_reported_outputs
from core.paths import (
    FROZEN,
    drop_session_dir,
    inputs_dir,
    logs_dir,
    outputs_root,
    read_build_sha,
    read_version,
    static_dir,
    templates_dir,
)
from core.progress import parse as parse_progress
from core.registry import (
    discover,
    discover_themes,
    scripts_for_file,
    theme_descriptions,
    theme_labels,
)
from webapp import _runs, _waveform
from webapp._badges import badges_for
from webapp._form import (
    accepts_directory,
    batch_mode_for,
    build_argv,
    field_specs_payload,
    fields_from_parser,
    file_input_for,
    spans_full_row,
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
templates.env.globals["host_is_mac"] = sys.platform == "darwin"


# The packaged app binds the same port on every launch, so every build shares
# one browser origin. Without this, the Chromium app window kept a stylesheet
# from an older build for days — the sidebar rendered with rules that no
# longer existed. no-cache still allows the ETag round-trip, so a 304 is the
# usual cost.
@app.middleware("http")
async def revalidate_static(request: Request, call_next):  # noqa: ANN001, ANN201
    """Make browsers revalidate static assets on every load.

    Args:
        request: Incoming request.
        call_next: The next handler in the middleware chain.

    Returns:
        The response, with ``Cache-Control: no-cache`` on ``/static`` paths.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


templates.env.globals["accepts_directory"] = accepts_directory
templates.env.globals["spans_full_row"] = spans_full_row


def _missing_capabilities(*, required_only: bool = True) -> tuple[capabilities.Capability, ...]:
    """Return absent dependencies for the sidebar banner.

    Indirection on purpose. Binding ``capabilities.missing`` into the Jinja
    globals directly captures the function object at import, which is the same
    early-binding mistake that made the old ffmpeg banner need a restart —
    just less visible, since the result would still look live.

    Args:
        required_only: Omit capabilities whose absence only costs an option.

    Returns:
        Absent capabilities.
    """
    return capabilities.missing(required_only=required_only)


def _capability_for_script(key: str) -> capabilities.Capability | None:
    """Return the dependency a script needs, probed now rather than at import.

    Args:
        key: Dotted script key.

    Returns:
        The capability, or None when the script needs nothing external.
    """
    return capabilities.for_script(key)


# Probing at import meant installing ffmpeg and reloading still showed the "not
# found" banner until the app was restarted. core.capabilities caches for a few
# seconds, so a render costs one probe at most.
templates.env.globals["missing_capabilities"] = _missing_capabilities
templates.env.globals["capability_for_script"] = _capability_for_script

# A callable, not a value: the globals below are evaluated once at import, but
# favourites change on every click. base.html calls this per render so the
# starred state is correct in the first paint rather than after a fetch.
templates.env.globals["user_preferences_json"] = lambda: json.dumps(
    {"favourites": (_c := load_config()).favourites, "sort_order": _c.sort_order}
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

    A packaged app has no repository to ask, so it reads the hash the build
    recorded instead (see ``packaging/build_sha.py``).

    Returns:
        Short hash string, or "—" on any failure.
    """
    if FROZEN:
        return read_build_sha() or "—"
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


def _themes_meta_json(themes: dict) -> str:
    """Serialise per-theme display metadata for client-side sorting.

    The browser needs each theme's label and script count to reorder sections
    without a round trip.

    Args:
        themes: Mapping of theme name → {script name → module}.

    Returns:
        JSON string with ``</`` escaped so it is safe inside a ``<script>`` tag.
    """
    labels = theme_labels()
    data = {
        theme: {
            "label": labels.get(theme, theme),
            "count": len(scripts),
            # Index-aligned with the same theme's entry in __THEMES__, so the
            # client can pair a script key with its searchable string.
            "keys": [f"{theme}.{name}" for name in scripts],
        }
        for theme, scripts in themes.items()
    }
    return json.dumps(data).replace("</", "<\\/")


_APP_VERSION = read_version()
_GIT_HASH = _read_git_hash()


def _browser_context(favourites_only: bool) -> dict:
    """Build the template context for the script browser.

    Shared by ``/`` and ``/favourites``: both render the same list, and which
    rows are shown is decided client-side from the starred set that base.html
    seeds out of ``UserConfig``.

    Args:
        favourites_only: Whether the page should start filtered to favourites.

    Returns:
        Template context dict.
    """
    themes = discover_themes()
    return {
        "themes": themes,
        "all_themes": themes,
        "labels": theme_labels(),
        "descriptions": theme_descriptions(),
        "themes_data_json": _themes_search_json(themes),
        "themes_meta_json": _themes_meta_json(themes),
        "total_scripts": sum(len(s) for s in themes.values()),
        "favourites_only": favourites_only,
        "version": _APP_VERSION,
        "git_hash": _GIT_HASH,
    }


@app.get("/")
async def index(request: Request):
    """List all available scripts grouped by theme."""
    return templates.TemplateResponse(request, "index.html", _browser_context(favourites_only=False))


@app.get("/favourites")
async def favourites(request: Request):
    """Show only the scripts the user has starred.

    Renders the same browser as ``/``; the filtering happens client-side.
    """
    return templates.TemplateResponse(request, "index.html", _browser_context(favourites_only=True))


@app.get("/history")
async def history_page(request: Request):
    """Show past runs, newest first, with re-run links."""
    records = history.load()
    known = discover()
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "records": records,
            # A script can be removed or renamed after a run; its history entry
            # stays, but there is nowhere to re-run it.
            "known_keys": {r.key for r in records if r.key in known},
            "titles": {key: mod.TITLE for key, mod in known.items()},
            "all_themes": discover_themes(),
            "labels": theme_labels(),
            "version": _APP_VERSION,
            "git_hash": _GIT_HASH,
        },
    )


@app.post("/api/history/clear")
async def clear_history() -> JSONResponse:
    """Delete every stored run record.

    Returns:
        JSON acknowledgement.
    """
    history.clear()
    return JSONResponse({"ok": True})


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
            # Only a script that can say which models a form state loads gets
            # the pre-run download notice; see /api/model-weights.
            "reports_model_weights": hasattr(mod, "models_for_args"),
        },
    )


# Content-length per weights URL. One HEAD per model per process is plenty;
# release assets do not change size.
_weights_sizes: dict[str, int | None] = {}


def _weights_size(url: str) -> int | None:
    """Ask the release server how big a weights file is.

    Args:
        url: The asset URL.

    Returns:
        Size in bytes, or None when offline or the server will not say. The
        notice then shows the model name without a number rather than guess.
    """
    if url in _weights_sizes:
        return _weights_sizes[url]
    size: int | None = None
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310
            length = response.headers.get("Content-Length")
            size = int(length) if length else None
    except Exception:
        size = None
    _weights_sizes[url] = size
    return size


@app.get("/api/model-weights/{theme}/{script_name}")
async def model_weights(theme: str, script_name: str, request: Request) -> JSONResponse:
    """Say which model weights the current form state would download.

    The script itself resolves the form into models via ``models_for_args``,
    so the answer tracks ``run()`` exactly — presets, overrides and
    compare-everything modes included.

    Args:
        theme: Script theme slug.
        script_name: Script module name.
        request: Request whose query params carry the current form values.

    Returns:
        JSON with ``downloads`` (absent models and their sizes, in run order)
        and ``weights_dir``.

    Raises:
        HTTPException: 404 if the script is unknown or does not report models.
    """
    key = f"{theme}.{script_name}"
    scripts = discover()
    mod = scripts.get(key)
    if mod is None or not hasattr(mod, "models_for_args"):
        raise HTTPException(status_code=404, detail=f"Script {key!r} does not report model weights")

    parser = mod.get_parser()
    argv = build_argv(dict(request.query_params), fields_from_parser(parser))
    try:
        # parse_known_args rather than parse_args: the subclass's parse_args
        # prints a startup banner to stderr, which belongs to a script run,
        # not to a form keystroke in the server log.
        args, _ = parser.parse_known_args(argv)
    except SystemExit:
        # A half-filled form is not an error; there is just nothing to say yet.
        return JSONResponse({"downloads": [], "weights_dir": str(capabilities.model_weights_dir())})

    downloads = []
    for model in mod.models_for_args(args):
        if capabilities.model_weights_present(model):
            continue
        url = mod.weights_url(model) if hasattr(mod, "weights_url") else None
        size = await asyncio.to_thread(_weights_size, url) if url else None
        downloads.append({"model": model, "size_bytes": size})

    return JSONResponse({"downloads": downloads, "weights_dir": str(capabilities.model_weights_dir())})


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
    # Underscore-prefixed params are for the runner, not the script. build_argv
    # only reads declared field specs, so this never reaches argv — popping it
    # keeps it out of the history record's params too.
    batch_id = form_data.pop("_batch_id", "")
    argv = build_argv(form_data, field_specs)
    handle = _runs.new_handle(key, argv, form_data, batch_id=batch_id)

    return StreamingResponse(
        _stream_script(handle),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# Names of capabilities whose install is currently running. winget refuses a
# second concurrent install anyway, and two buttons for one dependency racing
# each other would only produce a confusing pair of logs.
_installs_in_flight: set[str] = set()


@app.get("/api/capabilities/{name}/install")
async def install_capability(name: str) -> StreamingResponse:
    """Run a dependency's install command and stream its output.

    Args:
        name: Capability name from ``core.capabilities``.

    Returns:
        Server-Sent Events: the command's output lines, then a ``done`` event
        carrying the exit code and whether the capability is now present.

    Raises:
        HTTPException: 404 for an unknown capability, 409 when it has no
            unattended install command on this platform or is already being
            installed.
    """
    capability = capabilities.probe(name)
    if capability is None:
        raise HTTPException(status_code=404, detail=f"Unknown capability {name!r}")
    if not capability.command:
        raise HTTPException(status_code=409, detail=f"{capability.label} has no unattended install on this platform")
    if name in _installs_in_flight:
        raise HTTPException(status_code=409, detail=f"{capability.label} is already being installed")

    return StreamingResponse(
        _stream_install(name, capability.command),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_install(name: str, command: tuple[str, ...]):
    """Run an install command and yield its output as SSE events.

    Lines are sent raw, not HTML-escaped: the sidebar renders them as text,
    unlike the script terminal which takes markup. On success the process PATH
    is re-read so the new binary is found without a restart, and the ``done``
    event says whether the probe now passes.

    Args:
        name: Capability being installed.
        command: Argv to run.

    Yields:
        SSE-formatted byte strings.
    """
    _installs_in_flight.add(name)
    try:
        yield f"data: $ {' '.join(command)}\n\n".encode()
        try:
            proc = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **_runs.spawn_kwargs(),
            )
        except OSError as exc:
            yield f"data: {exc}\n\n".encode()
            payload = json.dumps({"exit_code": None, "present": False, "error": str(exc)})
            yield f"event: done\ndata: {payload}\n\n".encode()
            return

        async for line in proc.stdout:  # type: ignore[union-attr]
            # winget redraws its progress bar with carriage returns; only the
            # final state of such a line is worth showing.
            text = line.decode(errors="replace").rstrip().rsplit("\r", 1)[-1].strip()
            if text:
                yield f"data: {text}\n\n".encode()

        await proc.wait()
        capabilities.refresh_environment()
        present = capabilities.probe(name)
        payload = json.dumps(
            {
                "exit_code": proc.returncode,
                "present": bool(present and present.present),
            }
        )
        yield f"event: done\ndata: {payload}\n\n".encode()
    finally:
        _installs_in_flight.discard(name)


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> JSONResponse:
    """Stop a running script and everything it spawned.

    Args:
        run_id: Identifier from the stream's ``start`` event.

    Returns:
        JSON with ``cancelled`` reporting whether a process tree was signalled.

    Raises:
        HTTPException: 404 if no run with that id is currently in flight —
            which includes runs that have already finished.
    """
    handle = _runs.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="No such run in progress")

    # terminate_tree blocks (it waits out a SIGTERM grace period on POSIX).
    killed = await asyncio.to_thread(_runs.terminate_tree, handle)
    logger.info("Cancelled run %s (%s), signalled=%s", run_id, handle.key, killed)
    return JSONResponse({"run_id": run_id, "cancelled": killed})


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


@app.get("/api/waveform")
async def waveform(path: str, buckets: int = 900) -> JSONResponse:
    """Return a peak envelope for a staged media file's audio.

    Reading peaks here rather than in the page is what makes the ``av.trim``
    waveform work for every file the script accepts: ffmpeg is already required
    to do the trimming, whereas the browser's own decoder covers only the
    formats it was built with.

    Args:
        path: Server-side path of a staged input file.
        buckets: Number of peaks to return.

    Returns:
        ``{"duration": float, "peaks": [float, ...]}``. ``peaks`` is empty when
        the file has no audio track.

    Raises:
        HTTPException: 400/403/404 when the path is not a staged input, 422
            when the file cannot be decoded.
    """
    try:
        target = _waveform.resolve_staged_input(path, inputs_dir("av"))
    except _waveform.StagedInputError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    try:
        result = await asyncio.to_thread(_waveform.read_waveform, target, buckets)
    except _waveform.WaveformError as e:
        logger.info("Waveform unavailable for %s: %s", target.name, e)
        raise HTTPException(status_code=422, detail=str(e))
    return JSONResponse(result.as_dict())


@app.get("/api/staged-input")
async def staged_input(path: str) -> FileResponse:
    """Hand a staged input file back to the page that staged it.

    Exists for ``av.trim``'s play button on a file that arrived by drop
    prefill: the page never held a ``File`` for it, so the only way to decode
    it for playback is to fetch it. Same containment rule as the waveform
    endpoint — only files under the shared inputs root are served, so a page
    that can reach localhost cannot read the rest of the disk through this.

    Args:
        path: Server-side path of a staged input file.

    Returns:
        The file, for the browser to decode.

    Raises:
        HTTPException: 400/403/404 when the path is not a staged input.
    """
    try:
        target = _waveform.resolve_staged_input(path, inputs_dir("av"))
    except _waveform.StagedInputError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    return FileResponse(target, headers={"Cache-Control": "no-store"})


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
            "favourites": cfg.favourites,
            "sort_order": cfg.sort_order,
            "notify_telegram": cfg.notify_telegram,
            "notify_min_seconds": cfg.notify_min_seconds,
            "browse_supported": _webview_window(request) is not None,
        }
    )


@app.get("/api/keys")
async def get_keys() -> JSONResponse:
    """List the keys the app can hold, and whether each is set.

    A secret never leaves the server: the modal shows "set" or "not set" and a
    blank field. A plain identifier (a Telegram chat id) is returned, since the
    user has to be able to see which chat they pointed the bot at. Driven by
    the capability registry, so a new configure-remedy capability gets a field
    without UI work.

    Returns:
        JSON with ``keys``: one entry per configure-remedy capability.
    """
    keys = [
        {
            "name": c.name,
            "label": c.label,
            "env_var": c.env_var,
            "needed_for": c.needed_for,
            "is_set": c.present,
            "secret": c.secret,
            "value": "" if c.secret else os.environ.get(c.env_var, "").strip(),
        }
        for c in capabilities.probe_all()
        if c.remedy == capabilities.REMEDY_CONFIGURE and c.env_var
    ]
    return JSONResponse({"keys": keys})


@app.post("/api/notify-test")
async def notify_test() -> JSONResponse:
    """Send a test message to the configured Telegram chat.

    The only way to find out whether a token and chat id actually pair up is
    to send something, so the settings modal offers this next to the toggle.

    Returns:
        JSON with ``ok``; false when credentials are missing or Telegram
        refused the message.
    """
    from scripts.util.notify import send  # noqa: PLC0415

    ok = await asyncio.to_thread(send, "Scriptorium can reach this chat. Long runs will report here.")
    return JSONResponse({"ok": ok})


@app.post("/api/keys")
async def post_key(request: Request) -> JSONResponse:
    """Store or clear one key in the user ``.env``.

    Args:
        request: JSON body with ``name`` (a capability name) and ``value``;
            an empty value clears the key.

    Returns:
        JSON with ``is_set`` after the write, and ``value`` for a key that is
        not a secret.

    Raises:
        HTTPException: 404 when the name is not a key the app manages.
    """
    body = await request.json()
    name = str(body.get("name", ""))
    capability = capabilities.probe(name)
    if capability is None or capability.remedy != capabilities.REMEDY_CONFIGURE or not capability.env_var:
        raise HTTPException(status_code=404, detail=f"No such key {name!r}")
    set_env_value(capability.env_var, str(body.get("value", "")))
    capabilities.invalidate()
    refreshed = capabilities.probe(name)
    visible = "" if capability.secret else os.environ.get(capability.env_var, "").strip()
    return JSONResponse({"is_set": bool(refreshed and refreshed.present), "value": visible})


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
    """Persist the settings-modal fields to config.json.

    Favourites and sort order share the same file but are not in this form, so
    they are carried over from what is already stored — rebuilding UserConfig
    from the body alone would silently clear them every time the modal saves.
    """
    body = await request.json()
    existing = load_config()
    cfg = UserConfig(
        theme=body.get("theme", "light"),
        outputs_dir=body.get("outputs_dir", ""),
        close_behavior=body.get("close_behavior", "close"),
        favourites=existing.favourites,
        sort_order=existing.sort_order,
        notify_telegram=body.get("notify_telegram") is True,
        notify_min_seconds=clean_notify_min_seconds(body.get("notify_min_seconds", existing.notify_min_seconds)),
    )
    save_config(cfg)
    return JSONResponse({"ok": True})


@app.post("/api/preferences")
async def post_preferences(request: Request) -> JSONResponse:
    """Persist favourites and sort order.

    Separate from ``/api/settings`` because these change on a single click
    rather than a modal save, and each field is sent only when it changed.
    """
    body = await request.json()
    cfg = load_config()
    if "favourites" in body:
        cfg.favourites = clean_favourites(body["favourites"])
    if "sort_order" in body:
        cfg.sort_order = clean_sort_order(body["sort_order"])
    save_config(cfg)
    return JSONResponse({"ok": True, "favourites": cfg.favourites, "sort_order": cfg.sort_order})


def _is_revealable(target: Path) -> bool:
    """Report whether *target* is a path this server will open a window onto.

    Two things qualify: anything inside the managed outputs tree, and anything a
    past run was recorded as having written. The second is what covers a result
    the user sent somewhere of their own choosing, such as ``~/Downloads``,
    without turning the endpoint into "open any folder on this machine" for
    whatever else can reach localhost.

    Args:
        target: Already-resolved path to check.

    Returns:
        True when the path may be revealed.
    """
    try:
        if target.is_relative_to(outputs_root().resolve()):
            return True
    except OSError:
        return False
    for record in history.load():
        for known in record.outputs:
            try:
                if Path(known).resolve() == target:
                    return True
            except OSError:
                continue
    return False


@app.post("/api/reveal-output")
async def reveal_output(request: Request) -> JSONResponse:
    """Open a produced file's folder in the OS file manager.

    The path arrives from the client, so it is re-checked here rather than
    trusted. Detection ran server-side and only ever yields outputs, but this
    endpoint is reachable directly.

    Returns:
        JSON ``{"ok": true}``, or 400 for a path that is not a known output.
    """
    body = await request.json()
    raw = str(body.get("path", ""))
    try:
        target = Path(raw).resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="Not a usable path") from None
    if not _is_revealable(target):
        raise HTTPException(status_code=400, detail="Path is not a known output")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File no longer exists")
    _open_in_file_manager(target.parent)
    return JSONResponse({"ok": True})


@app.post("/api/reveal-run-outputs")
async def reveal_run_outputs(request: Request) -> JSONResponse:
    """Open the folders one run wrote into.

    Takes a run id rather than a path so there is nothing to validate: the
    folders come from what the server itself recorded for that run. Almost every
    run writes to a single directory, but a script given both an explicit file
    and a batch destination can produce two, and both are worth opening.

    Returns:
        JSON ``{"ok": true, "folders": [...]}``, or 404 when the run recorded no
        surviving output files.
    """
    body = await request.json()
    run_id = str(body.get("run_id", ""))
    record = next((r for r in history.load() if r.run_id == run_id), None)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown run")

    folders: list[Path] = []
    for known in record.outputs:
        path = Path(known)
        if path.is_file() and path.parent not in folders:
            folders.append(path.parent)
    if not folders:
        raise HTTPException(status_code=404, detail="This run has no surviving output files")

    for folder in folders:
        _open_in_file_manager(folder)
    return JSONResponse({"ok": True, "folders": [str(f) for f in folders]})


@app.get("/api/recent-outputs/{theme}/{script_name}")
async def recent_outputs(theme: str, script_name: str, limit: int = 5) -> JSONResponse:
    """List files recent runs of one script produced and that still exist.

    Args:
        theme: Script theme slug.
        script_name: Script module name.
        limit: Most files to return.

    Returns:
        JSON ``{"outputs": [{path, name, when}]}``, newest first.
    """
    key = f"{theme}.{script_name}"
    seen: dict[str, dict] = {}
    for record in history.load():
        if record.key != key:
            continue
        for path in record.outputs:
            if path in seen:
                continue
            if not Path(path).is_file():
                continue  # cleaned up since the run
            seen[path] = {"path": path, "name": Path(path).name, "when": record.started_at}
            if len(seen) >= limit:
                return JSONResponse({"outputs": list(seen.values())})
    return JSONResponse({"outputs": list(seen.values())})


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


def _status_for(handle: _runs.RunHandle, exit_code: int | None) -> str:
    """Classify how a run ended.

    A cancelled process still exits non-zero, so the handle's own flag has to
    win over the exit code — otherwise every cancellation looks like a crash.

    Args:
        handle: The run's handle.
        exit_code: Process exit code, if any.

    Returns:
        One of the ``core.history`` status constants.
    """
    if handle.cancelled:
        return history.CANCELLED
    return history.SUCCESS if exit_code == 0 else history.ERROR


async def _stream_script(handle: _runs.RunHandle):
    """Run a script as a subprocess and yield its output as SSE events.

    Emits a 'start' event carrying the run id (so the client can cancel), then
    stdout lines, then stderr lines, each HTML-escaped. A final 'done' event
    reports the exit code, elapsed time and whether the run was cancelled.

    Stdout lines that turn out to be ``core.progress`` sentinels are pulled out
    and re-emitted as 'progress' events instead, so they drive the status bar
    rather than appearing as terminal noise.

    The run is recorded in history and dropped from the live registry however
    it ends, including on cancellation.

    Args:
        handle: Registered handle describing the run to start.

    Yields:
        SSE-formatted byte strings.
    """
    import time  # noqa: PLC0415

    if FROZEN:
        cmd = [sys.executable, "--run-script", handle.key, *handle.argv]
        cwd = None
    else:
        cmd = [sys.executable, str(_REPO_ROOT / "main.py"), handle.key, *handle.argv]
        cwd = str(_REPO_ROOT)

    # Scripts resolve relative inputs and default outputs differently depending
    # on who asked. The development command line above is exactly what a human
    # types, so the marker has to be out-of-band rather than an argument.
    env = webapp_spawn_env()

    t0 = time.monotonic()
    # Wall-clock twin of t0, used to tell a file this run wrote from one it only
    # echoed. Backdated a little because mtime granularity is coarser than this
    # clock on some filesystems, and losing a real output is worse than the
    # occasional stale one.
    started_wall = time.time() - 2
    yield f"event: start\ndata: {json.dumps({'run_id': handle.run_id})}\n\n".encode()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            **_runs.spawn_kwargs(),
        )
        handle.process = proc

        # Collected unescaped and separately from the stream: output detection
        # needs the raw text, and once a line has been HTML-escaped a path with
        # an ampersand in it is no longer a path.
        stdout_lines: list[str] = []

        async for line in proc.stdout:  # type: ignore[union-attr]
            raw = line.decode(errors="replace").rstrip()

            # A progress line is a report about the run, not part of its output.
            # It never reaches the terminal, and never reaches output detection.
            event = parse_progress(raw)
            if event is not None:
                payload = json.dumps({"fraction": event.fraction, "label": event.label})
                yield f"event: progress\ndata: {payload}\n\n".encode()
                continue

            stdout_lines.append(raw)
            yield f"data: {html.escape(raw)}\n\n".encode()

        async for line in proc.stderr:  # type: ignore[union-attr]
            text = html.escape(line.decode(errors="replace").rstrip())
            yield f"data: <span class='stderr'>{text}</span>\n\n".encode()

        await proc.wait()
        rc = proc.returncode
        elapsed = round(time.monotonic() - t0, 1)
        status = _status_for(handle, rc)

        # Only a clean run is credited with outputs. A cancelled transcode
        # leaves a truncated file behind, and offering that as a result is
        # worse than saying nothing.
        detected = (
            [str(p) for p in find_reported_outputs(stdout_lines, since=started_wall)]
            if status == history.SUCCESS
            else []
        )

        if status == history.CANCELLED:
            yield b"data: <span class='exit-err'>cancelled</span>\n\n"
        else:
            css = "exit-ok" if rc == 0 else "exit-err"
            yield f"data: <span class='{css}'>exit {rc}</span>\n\n".encode()

        history.append(
            history.RunRecord(
                run_id=handle.run_id,
                key=handle.key,
                status=status,
                started_at=handle.started_at.isoformat(timespec="seconds"),
                elapsed=elapsed,
                exit_code=rc,
                argv=handle.argv,
                params=handle.params,
                outputs=detected,
                batch_id=handle.batch_id,
            )
        )

        done_payload = json.dumps(
            {
                "exit_code": rc,
                "elapsed": elapsed,
                "status": status,
                "cancelled": status == history.CANCELLED,
                "run_id": handle.run_id,
                "outputs": [{"path": p, "name": Path(p).name} for p in detected],
            }
        )
        yield f"event: done\ndata: {done_payload}\n\n".encode()
    finally:
        _runs.discard(handle.run_id)


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
