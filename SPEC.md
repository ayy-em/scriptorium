# Scriptorium — Technical Spec

## What this is

A single-entrypoint collection of themed utility scripts. All execution — CLI or
programmatic — goes through `core/runner.py`, which provides a uniform middleware
layer (currently: timing). Scripts themselves stay lean: no cross-cutting logic,
no `sys.exit` outside of `run()`.

---

## Repository layout

```
scriptorium/
├── build.sh                 # unified build entrypoint (detects OS, delegates)
├── main.py                  # CLI entrypoint
├── inputs/                  # drop files here (shared across every theme)
│   └── processed/           # files auto-archived here after successful runs
├── outputs/                 # per-theme outputs land here as <theme>/<file>
├── core/
│   ├── argparse.py          # ScriptoriumParser with ui_label support
│   ├── config.py            # user settings persistence (UserConfig, load, save)
│   ├── history.py           # run history persistence (RunRecord, load, append)
│   ├── env.py               # centralized .env loading
│   ├── outputs.py           # standardized output path resolution
│   ├── paths.py             # centralized path resolution (frozen vs dev)
│   ├── registry.py          # auto-discovers scripts and themes
│   └── runner.py            # dispatch + middleware (run, run_fn)
├── scripts/
│   └── <theme>/
│       ├── __init__.py      # LABEL, DESCRIPTION
│       ├── _helpers.py      # private shared code (ignored by registry)
│       └── <script>.py      # one script per file
├── webapp/
│   ├── app.py               # FastAPI server
│   ├── _badges.py           # ACCEPTS-derived compatibility badges
│   ├── _form.py             # argparse introspection for auto-generated forms
│   ├── _icons.py            # PNG icon lookup for scripts and file categories
│   ├── _runs.py             # live run registry + process-tree termination
│   ├── static/
│   │   ├── style.css        # the entire stylesheet, sectioned (see below)
│   │   ├── fonts/           # self-hosted Inter + JetBrains Mono (OFL 1.1)
│   │   ├── js/              # vendored Alpine.js + focus plugin
│   │   ├── icons/           # legacy PNG icons (see BACKLOG.md)
│   │   └── logo.{png,webp}
│   └── templates/           # Jinja2 (see "Web UI layer" below)
└── packaging/
    ├── entrypoint.py            # frozen app entry (web server + --run-script mode)
    ├── scriptorium.spec         # PyInstaller spec for macOS .app bundle
    ├── scriptorium-win.spec     # PyInstaller spec for Windows folder bundle
    ├── scriptorium-linux.spec   # PyInstaller spec for Linux binary
    ├── build.sh                 # macOS build script
    ├── build_installer.bat      # Windows build script (PyInstaller + Inno Setup)
    ├── build_linux.sh           # Linux build script
    └── installer.iss            # Inno Setup script for Windows installer
```

Local data lives at the repo root: a single `inputs/` directory shared across
every theme, an `outputs/` directory with one subdirectory per theme
(`outputs/<theme>/`), and `inputs/processed/` where files are auto-archived
after a successful run. The `inputs/` and `outputs/` folders themselves are
tracked via `.gitkeep`; their contents are gitignored.

---

## Invocation

### CLI

```sh
uv run main.py                          # list all scripts across all themes
uv run main.py <theme>                  # list scripts in one theme with descriptions
uv run main.py <theme>.<script> [args]  # run a script
uv run main.py <theme>.<script> --help  # show usage, arguments, and examples
```

`uv run` is the only supported CLI invocation — use it on all platforms.

#### Theme listing output format

`uv run main.py <theme>` prints the theme's description first, then the script list:

```
Audio and video processing backed by ffmpeg

Theme 'av' (10 script(s)):

  av.convert                                Convert media file to a different format
                                            Transcode a file (or directory of files) to a target container/codec.

  av.trim                                   Trim media file
                                            Cut a video or audio file to a start/end timestamp.
  ...

Run 'uv run main.py av.<script> --help' for usage details.
```

### Webapp

```sh
uv run webapp                           # start the local web UI (default: http://127.0.0.1:8000)
uv run webapp --port 9000               # custom port
```

The web UI lists all scripts grouped by theme, with live search, sortable
categories, favourites, and dark/light mode. Clicking a script opens a detail
page with an auto-generated form (built from `get_parser()`). Path-typed
arguments render as drag-and-drop file upload fields (except `--output` and
`--inputs` directory args, which remain text fields). Submitting the form runs
the script and streams its output via SSE, which can be cancelled mid-run;
completed runs are recorded and re-runnable from `/history`.

Uploaded files are saved to the theme's inputs directory via `POST /upload/{theme}`.

When ffmpeg is not found on PATH, a banner appears in the sidebar with install
instructions.

---

## Web UI layer

No build step. Jinja2 templates, one stylesheet, and Alpine.js — all served
locally so the packaged app works offline.

### Third-party assets, vendored

| Asset | Version | Path | Licence |
|---|---|---|---|
| Alpine.js | 3.15.12 | `static/js/alpinejs.min.js` | MIT |
| Alpine Focus plugin | 3.15.12 | `static/js/alpinejs-focus.min.js` | MIT |
| Inter (variable, latin) | — | `static/fonts/inter-latin-wght-normal.woff2` | SIL OFL 1.1 |
| JetBrains Mono (variable, latin) | — | `static/fonts/jetbrains-mono-latin-wght-normal.woff2` | SIL OFL 1.1 |

The focus plugin must load **before** Alpine core; it supplies `x-trap`, which
the settings modal uses for focus trapping. Fonts total ~89KB. PyInstaller
bundles `webapp/static` wholesale, so vendored assets need no spec changes.

### Templates

```
templates/
├── base.html              # shell: topnav, sidebar slot, $store.ui, splash
├── index.html             # script browser + Drop-to-Discover (scriptBrowser())
├── script.html            # script detail page (scriptRunner())
├── history.html           # past runs with re-run links
├── _splash.html           # boot overlay, plain JS — see below
├── _icons.html            # icon(name, size, cls) — inline SVG UI icon set
├── _components.html       # badge(), empty_state(), soon_button()
├── _macros.html           # theme_icon() — still partly PNG-backed
├── _settings_modal.html   # settings dialog
├── _script_form.html      # auto-generated argument form
├── _script_context.html   # right-hand context column
├── _terminal.html         # run status strip + streaming console
├── _sidebar.html, _onboarding_modal.html, _howto_modal.html
├── _drop_{overlay,chooser,runner}.html
└── scripts/av/trim.html   # hand-written override via a script's TEMPLATE attr
```

`webapp/static/style.css` is one file, sectioned with a table of contents at the
top. **Design tokens are defined in pairs**: every custom property in `:root`
has a matching entry in `html.dark`. Adding one without the other is a bug.

### Client-side state

These live in `localStorage` rather than `UserConfig`, because none of them needs
the server:

| Key | Shape | Notes |
|---|---|---|
| `favourites` | array of script keys | `["av.filmstrip", …]` |
| `sort_order` | `"az"` \| `"za"` \| `"count"` | validated against `SORT_ORDERS` on load |
| `theme` | `"light"` \| `"dark"` | mirrors `UserConfig.theme` to avoid a dark-mode flash |
| `onboarding_seen` | `"1"` | |

Consequence: they are **per browser profile**, and the three launch tiers do not
share storage. See BACKLOG.md — moving favourites into `UserConfig` is the fix
if that becomes annoying.

Because the server never sees favourites, `/favourites` renders every script and
Alpine hides the rest; `[x-cloak]` covers the pre-init frame. `__THEME_META__`
carries each theme's label, script count and script keys — index-aligned with
that theme's entry in `__THEMES__` — so the client can filter and reorder
without a round trip. Sections reorder via the flex `order` property, so no DOM
nodes move.

### Splash screen

`_splash.html` covers the window until Alpine initialises, replacing the
unstyled `[x-cloak]`-blanked first paint. It is driven by **plain JS, not
Alpine** — an Alpine-driven splash could never dismiss itself if Alpine were the
thing that failed. It clears when Alpine initialises and fonts are ready, with a
1.2s font timeout, and falls back to a retry/open-logs error state after 4s.

### Web endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | script browser |
| `GET /favourites` | the same browser, client-filtered to starred scripts |
| `GET /scripts/{theme}/{script_name}` | detail page + generated form |
| `GET /scripts/{theme}/{script_name}/run` | run the script, stream output as SSE |
| `POST /api/runs/{run_id}/cancel` | kill a running script and its whole process tree |
| `GET /history` | past runs, newest first, with re-run links |
| `POST /api/history/clear` | delete every stored run record |
| `GET /api/script-fields/{theme}/{script_name}` | field specs, minus the file input |
| `GET /api/preview-command/{theme}/{script_name}` | CLI equivalent of the current form state |
| `POST /upload/{theme}` | single-file upload |
| `POST /api/drop-upload` | multi-file drop; returns matching scripts |
| `GET`/`POST /api/settings` | read/write `UserConfig` |
| `POST /api/browse-folder` | native folder picker; 501 outside the desktop app |
| `POST /api/open-outputs` | reveal the outputs root |
| `POST /api/open-logs` | reveal the logs directory |
| `POST /api/quit` | shut the server down (frozen mode only) |
| `GET /api/update-check` | compare against the latest GitHub release |

`preview-command` shares `webapp._form.build_argv` with the run endpoint, so the
previewed command cannot drift from what actually executes. It quotes with
`subprocess.list2cmdline` on Windows and `shlex.join` elsewhere, and prefixes
`scriptorium` when frozen, `uv run main.py` otherwise.

`browse-folder` requires `app.state.webview_window`, set by
`packaging/entrypoint.py` only on the pywebview tier. A browser cannot return an
absolute directory path, so on the other two launch tiers the endpoint returns
501 and the UI disables the button.

### Run output classification

`_stream_script` yields stdout lines, then stderr lines wrapped in
`<span class='stderr'>`, then an exit line and a `done` event carrying
`{exit_code, elapsed}`. The client maps these to console severities.

One special case: `core/runner.py` writes its own run banner
(`[av.filmstrip] done in 1.2s`) to **stderr** as routine progress. Without
handling, every successful run would render as a wall of warnings, so the client
demotes lines matching `^\[<key>\] ` to info — unless they say `failed`.

There is no output-artifact detection; the UI states as much rather than
implying otherwise. Tracked in BACKLOG.md.

---

## Run lifecycle

### Cancellation

A run is not one process. `main.py` spawns the script, which shells out to
ffmpeg or yt-dlp — so killing the direct child leaves the real worker running
and writing to disk. On Windows this is not a subtlety: `Process.kill()` is an
alias for `terminate()`, which calls `TerminateProcess` on that PID alone.

`webapp/_runs.py` therefore kills the tree:

| Platform | Spawn (`spawn_kwargs()`) | Kill |
|---|---|---|
| Windows | `creationflags=CREATE_NO_WINDOW` | `taskkill /T /F /PID` — `/T` walks the tree |
| POSIX | `start_new_session=True` — child leads its own process group | `killpg(SIGTERM)`, then `SIGKILL` after a 3s grace |

Flow: `run_script` mints a `run_id` and registers a `RunHandle`;
`_stream_script` emits `event: start` carrying that id before any output;
`POST /api/runs/{run_id}/cancel` looks the handle up and kills the tree.
A finished run is discarded from the registry, so cancelling it returns 404.

A killed process still exits non-zero, so `handle.cancelled` — not the exit
code — decides whether an ending is a cancellation or a failure.

Cancel deliberately leaves partial output files in place, and navigating away
mid-run still lets the script finish. Both are choices, not omissions.

### History

`core/history.py` stores completed runs in `~/scriptorium/history.json`
alongside `config.json`, newest first, capped at `MAX_ENTRIES` (200). It holds
no live process state — a `RunRecord` is a plain value: key, argv, params,
status, exit code, start time, elapsed.

`argv` is what actually ran; `params` is what the user typed. Re-run needs the
latter, which is why both are stored.

A corrupt file degrades to an empty history rather than raising, and a single
malformed entry is skipped instead of discarding the rest.

### Re-run

Re-run is a **link**, not an endpoint:
`/scripts/{theme}/{script}?_rerun=1&<params>`. It reuses the query-param
prefill the Drop-to-Discover flow already had; `_applyPrefill()` triggers on
either `_prefill_file` or `_rerun`. It lands on a filled-in form rather than
firing immediately — re-running a long transcode from one unseen click is a
footgun. Stored paths may no longer exist; the script reports that itself.

### Building a standalone app

```sh
bash build.sh
```

A unified build entrypoint in the repo root. It detects the OS via `uname` and
delegates to the platform-specific pipeline. On macOS it auto-installs missing
tools (uv, Homebrew, ffmpeg) before building. On Windows it validates that Inno
Setup is available, then delegates to `packaging/build_installer.bat`.

| Platform | Shell | Output |
|----------|-------|--------|
| macOS | Terminal / zsh | `dist/Scriptorium.app` |
| Windows | Git Bash | `dist/ScriptoriumSetup.exe` |
| Linux | bash | `dist/scriptorium-linux-x86_64.tar.gz` |

A GitHub Actions workflow (`.github/workflows/release.yml`) builds all three
platforms and uploads artifacts to a GitHub Release on tag push (`v*`).

The platform-specific scripts below can still be invoked directly.

### macOS app

```sh
bash packaging/build.sh                 # → dist/Scriptorium.app
```

The `.app` bundle uses PyInstaller. On launch it finds a free port, starts
uvicorn, and tries three display tiers in order:
1. **pywebview** native window (WKWebView on macOS, EdgeChromium on Windows)
2. **Chromium `--app` mode** — chromeless window via Chrome/Edge/Chromium
3. **Default browser** fallback — user quits via the sidebar Quit button

Scripts run as subprocesses via the frozen binary's `--run-script` flag (same
binary, different argv). The sidebar hides the CLI usage section and shows a
Quit button when running in frozen mode. A `/api/quit` endpoint (frozen-only)
allows the UI to signal the server to shut down.

#### CLI vs GUI dispatch

One binary serves both modes, so `packaging/entrypoint.py` has to decide which
the user meant. In order:

| Condition | Mode |
|---|---|
| `--run-script <key>` | CLI (internal subprocess dispatch) |
| Any other argument present | CLI |
| Bare launch, stdout is a tty | CLI (lists all scripts) |
| Bare launch, stdout is not a tty | GUI |

The tty check is the load-bearing part, and it must not be weakened back to
`sys.stdout is not None`. Only a Windows windowed build gets `None` streams; a
macOS `.app` launched from Finder inherits valid stdio from launchd pointed at
`/dev/null`, so the `None` check sent every Finder launch into the CLI, which
printed the script list to nowhere and exited — a dock bounce and no window.
`-psn_0_<pid>`, which LaunchServices may append, is stripped before the argument
check so it is not mistaken for a script key.

#### Tray icon threading

`close_behavior = "tray"` keeps the app resident when the window closes. The
threading model is platform-specific by necessity: pystray's macOS backend calls
`-[NSApplication run]` inside `Icon.run`, and AppKit aborts the process with
SIGTRAP if that happens off the main thread — a signal, so no `except` can
contain it.

| Tier | macOS | Windows / Linux |
|---|---|---|
| 1 — pywebview | `run_detached()`, serviced by the shared `NSApplication` that `webview.start()` runs | `Icon.run` on a background thread |
| 2 — Chromium `--app` | no tray (no GUI main loop to service an `NSStatusItem`) | `Icon.run` on a background thread |

See BACKLOG.md for the tier-2 macOS gap.

On startup the app checks GitHub Releases for a newer version and shows a
banner in the sidebar if an update is available.

#### macOS build details

| Item | Value |
|------|-------|
| Build script | `packaging/build.sh` |
| PyInstaller spec | `packaging/scriptorium.spec` |
| Output | `dist/Scriptorium.app` |
| Prerequisites | Python 3.14, uv, Xcode command-line tools |
| Webview backend | pywebview + Cocoa (WKWebView) |

The build script runs three steps: `uv sync --all-extras` (install all optional
dependencies), `uv pip install pyinstaller`, and `pyinstaller packaging/scriptorium.spec`.
The resulting `.app` is unsigned — on a Mac that did not build it, the quarantine
flag must be cleared before launch: `xattr -cr dist/Scriptorium.app`.

### Windows app

```cmd
packaging\build_installer.bat           # → dist\ScriptoriumSetup.exe
```

The Windows build uses PyInstaller in folder-bundle mode (no macOS `BUNDLE`
step). The entry point is the same `packaging/entrypoint.py` with the same
3-tier window cascade: pywebview, Chromium `--app` mode (Edge/Chrome),
then default browser fallback.

#### Windows build details

| Item | Value |
|------|-------|
| Build script | `packaging/build_installer.bat` |
| PyInstaller spec | `packaging/scriptorium-win.spec` |
| Inno Setup script | `packaging/installer.iss` |
| Output | `dist/ScriptoriumSetup.exe` |
| Prerequisites | Python 3.14, uv, Inno Setup 6+ (`iscc` on PATH) |
| Webview backend | pywebview + EdgeChromium (falls back to browser) |

`build_installer.bat` runs the full pipeline: dependency sync, PyInstaller
folder bundle, and Inno Setup compilation — producing a single
`ScriptoriumSetup.exe` in one command.

The installer supports two privilege modes via a dialog shown at launch:

| Mode | Install path | Elevation |
|------|-------------|-----------|
| Install for all users | `C:\Program Files\Scriptorium` | UAC admin prompt |
| Install just for me | `%LOCALAPPDATA%\Programs\Scriptorium` | None |

Both modes create Start Menu shortcuts and optionally add the install directory
to the user's PATH for CLI usage. Silent installs can select mode via
`/allusers` or `/currentuser` command-line switches.

### Linux binary

```sh
bash packaging/build_linux.sh           # → dist/scriptorium-linux-x86_64.tar.gz
```

#### Linux build details

| Item | Value |
|------|-------|
| Build script | `packaging/build_linux.sh` |
| PyInstaller spec | `packaging/scriptorium-linux.spec` |
| Output | `dist/scriptorium-linux-x86_64.tar.gz` |
| Prerequisites | Python 3.14, uv |
| Webview backend | pywebview + GTK (falls back to Chromium `--app` or browser) |

Extract the tarball and run `./scriptorium`. The app detects Chrome, Chromium,
or Edge on PATH for the `--app` mode window. If none are found, it opens the
default browser.

### Programmatic

```python
from scripts.<theme>.<script> import <function>
from core.runner import run_fn

result = run_fn(some_fn, arg1, arg2, kwarg=value)
```

`run_fn` applies the same middleware as the CLI path (timing, future hooks).
Use direct imports only in tests.

---

## Theme package anatomy

Each `scripts/<theme>/` directory is a Python package. Its `__init__.py` must define:

| Name          | Type   | Purpose                                                             |
|---------------|--------|---------------------------------------------------------------------|
| `LABEL`       | `str`  | Display name used in the web UI sidebar and CLI listings            |
| `DESCRIPTION` | `str`  | One-line tagline shown below the theme name in the web UI and at the top of `uv run main.py <theme>` output |
| `HIDDEN`      | `bool` | *(optional, default `False`)* When `True`, the theme is excluded from the UI, CLI listings, and discovery |

The module docstring is conventional documentation — it is not used by the runtime.

```python
"""A/V manipulation scripts backed by ffmpeg."""

LABEL = "A/V"
DESCRIPTION = "Audio and video processing backed by ffmpeg"
```

`theme_labels()` and `theme_descriptions()` in `core/registry.py` read these
attributes at runtime. Both fall back gracefully if an attribute is absent.
Themes with `HIDDEN = True` are filtered out by all registry functions.

---

## inputs / outputs convention

Every theme reads from and writes to a shared layout rooted at the repo:

```
inputs/             # drop source files here (shared across every theme)
    processed/      # successful runs auto-archive their inputs here
outputs/
    <theme>/        # results land here, one subdirectory per theme
```

Scripts resolve a bare filename (no directory component in the path) against
`inputs/` automatically, so users can type just a filename:

```sh
uv run main.py av.convert clip.mp4 --to mp3   # resolves to inputs/clip.mp4
```

### Post-processing: archiving input files

Every script that accepts a file as input **must** move the processed file to
`inputs/processed/<category>/` after a successful run. The archived filename
should include a date tag so multiple runs don't collide — the convention is
`<stem>_DDMMYY<ext>` using the UTC run-start date (with an `_HHMMSS` suffix
appended on same-day collisions).

Only files that live inside the shared `inputs/` tree are archived — files
passed via an absolute path outside the inputs root are left in place.

```
inputs/
    result.json              ← before run
    processed/
        telegram/
            result_210526.json   ← after successful run (21 May 2026 UTC)
```

### `core.paths` — centralized path resolution

All path resolution goes through `core.paths`, which detects whether the app is
running as a frozen PyInstaller bundle or in development. `inputs_dir()` is
theme-agnostic (every script shares the same inputs folder); `outputs_dir()`
remains keyed by theme; `past_inputs_dir()` always points at the same
`inputs/processed/` archive:

| Mode   | `inputs_dir("av")` | `outputs_dir("av")`         | `past_inputs_dir("av")`        |
|--------|--------------------|-----------------------------|--------------------------------|
| Dev    | `inputs/`          | `outputs/av/`               | `inputs/processed/`            |
| Frozen | `~/scriptorium/inputs/` | `~/scriptorium/outputs/av/` | `~/scriptorium/inputs/processed/` |

Theme helpers delegate to `core.paths`:

```python
from core.paths import inputs_dir, outputs_dir

def av_inputs_dir() -> Path:
    return inputs_dir("av")
```

`core.paths` also provides `templates_dir()`, `static_dir()`, `has_ffmpeg()`,
`read_version()`, and the `FROZEN` boolean.

### `core.outputs` — standardized output path resolution

All scripts use `core.outputs` for output file naming and placement. The module
provides four functions:

| Function | Purpose |
|----------|---------|
| `default_stem()` | Returns `YYYYMMDD_HHmm` timestamp string for default filenames |
| `deduplicate(path)` | Appends `_001`–`_999` suffix if `path` already exists |
| `resolve_output(output, *, theme, ext)` | Resolves a user-provided `--output` value (or `None`) to a concrete file path |
| `resolve_output_dir(output, *, theme)` | Same, but resolves to a directory (for multi-file output scripts) |

`resolve_output` handles three input shapes:

| User provides | Behaviour |
|---------------|-----------|
| Nothing (`None`) | `outputs/<theme>/YYYYMMDD_HHmm.ext` |
| Directory path | `<dir>/YYYYMMDD_HHmm.ext` |
| Filename only (no directory) | `outputs/<theme>/<filename>` |
| Full path with directory | Used as-is |

All scripts expose a single `--output` / `-o` flag (replacing the former
`--outputs` directory flag). Scripts that produce a single file use
`resolve_output()`; scripts that produce multiple files use
`resolve_output_dir()` combined with `default_stem()` for indexed naming
(e.g. `20260620_1706_001.mp4`, `20260620_1706_002.mp4`).

---

## Script anatomy

Every file the registry picks up must expose three names at module level:

| Name          | Type       | Purpose                                      |
|---------------|------------|----------------------------------------------|
| `TITLE`       | `str`      | One-line label shown in `uv run main.py`     |
| `DESCRIPTION` | `str`      | Sentence shown in `--help` and theme listing |
| `run()`       | `Callable` | CLI entrypoint — owns argparse + `sys.exit`  |

### Optional: `ACCEPTS`

Scripts that operate on dropped files declare which file categories they handle:

```python
ACCEPTS: set[str] = {"video", "audio"}
```

Valid categories are defined in `core/categories.py`: `video`, `audio`, `image`,
`tabular`, `document`. When present, the script appears on the Drop-to-Discover
wheel when a user drops a matching file onto the index page. Scripts without
`ACCEPTS` are excluded from drop results.

#### Batch classification

How a script behaves when several files are dropped is **inferred**, not
declared — `webapp._form.batch_mode_for()` reads it off the argument parser:

| Batch mode | Inferred from | Behaviour |
|---|---|---|
| `directory` | file input has widget `file-multi` (an optional `Path` positional), or its dest is `inputs` | one invocation against the drop session directory |
| `per_file` | file input has widget `file` | not yet implemented; the card renders dimmed |

To make a new script batch-capable, give its source argument `nargs="?"` and
have it accept a directory, as the `formats.convert_*` scripts do. Per-file
fan-out is tracked in `BACKLOG.md`.

#### Drop sessions

Every drop or clipboard paste writes into its own directory,
`inputs/drop/<timestamp>-<random>/` (see `core.paths.drop_session_dir`), so a
directory-native script never sees files from an earlier drop. All files in one
drop must share a category; mixed batches are rejected by `/api/drop-upload`.

### Optional: `get_parser()`

Scripts may also expose:

```python
def get_parser() -> argparse.ArgumentParser: ...
```

When present, the web UI uses it to auto-generate an argument form.
`run()` should call `get_parser().parse_args()` instead of constructing the parser
inline, so the two stay in sync automatically.

| Name           | Type       | Purpose                                                  |
|----------------|------------|----------------------------------------------------------|
| `get_parser()` | `Callable` | Returns the script's `ArgumentParser` without parsing    |

### `run()` — CLI only

- Parses `sys.argv` via `argparse`
- Calls the script's public function(s) with resolved arguments
- Calls `sys.exit(0/1)` to signal success or failure
- Contains no business logic
- Any file/directory input whose `Path.parent == Path(".")` (bare name, no directory
  component) is resolved to `<theme>/inputs/<name>` before being passed to the
  public function. This lets users type just a filename instead of the full path
  when the file lives in the conventional inputs directory.
- `ArgumentParser` must always be constructed with:
  - `prog="uv run main.py <theme>.<script>"` — fixes the usage line shown in `--help`
  - `formatter_class=argparse.RawDescriptionHelpFormatter` — preserves epilog formatting
  - `epilog=_EXAMPLES` — a module-level constant with 2–4 concrete example invocations

### Public functions — programmatic API

- Accept typed `Path` / primitive arguments — no argparse, no `sys.exit`
- Raise exceptions on unrecoverable errors (or return a meaningful value)
- Named for what they do (`validate`, `export`, `import_captions`, …)
- Are the unit under test

### Custom UI labels (`ui_label`)

By default the web UI derives form field labels from the flag name
(`--fade-in` → "Fade in"). When the auto-derived label is misleading or
too terse, pass `ui_label` to `add_argument()` to override it:

```python
parser.add_argument("--audio", action="store_true", ui_label="Audio only")
```

`ScriptoriumParser` from `core.argparse` is the mandatory parser for all
scripts. It is a drop-in replacement for the stdlib `ArgumentParser` that
adds `ui_label` support and the startup arg banner (see Runner middleware).

### Minimal example

```python
import argparse
import sys
from pathlib import Path

from core.argparse import ScriptoriumParser

TITLE = "Do a thing"
DESCRIPTION = "Does the thing to a file."

_EXAMPLES = """
examples:
  uv run main.py <theme>.do_thing file.txt
  uv run main.py <theme>.do_thing file.txt --verbose
"""


def do_thing(path: Path) -> int:
    ...
    return count


def get_parser() -> argparse.ArgumentParser:
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py <theme>.do_thing",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("path", type=Path)
    return parser


def run() -> None:
    args = get_parser().parse_args()
    count = do_thing(args.path)
    sys.exit(0 if count > 0 else 1)
```

---

## Runner middleware

All calls through `run()` or `run_fn()` are timed. Output goes to stderr so it
does not pollute captured stdout (e.g. JSON output piped to another process).

Every CLI script prints a startup banner before doing any work:

```
[lora.export_captions] started at 22-05-26 14:30
  inputs = inputs/lora
  output = captions.json
[lora.export_captions] done in 0.012s
```

The first line (timestamp) is emitted by `_timed` in `core/runner.py` — the
single bottleneck all execution paths pass through. The resolved-arguments block
is emitted by `ScriptoriumParser.parse_args()` in `core/argparse.py`, which
prints every argument and its resolved value to stderr immediately after parsing.

All scripts must use `ScriptoriumParser` (from `core.argparse`) instead of the
stdlib `ArgumentParser` so they inherit the startup banner automatically.

To add cross-cutting behaviour (logging, metrics, retries, …): edit `_timed` in
`core/runner.py`. It is the single place.

---

## Private helpers

Files whose names start with `_` are ignored by the registry. Use them for shared
constants or functions within a theme:

```
scripts/lora/_dataset.py   # IMAGE_EXTS, find_images(), find_captions()
scripts/av/_utils.py       # MEDIA_EXTS, run_ffmpeg(), av_inputs_dir(), …
```

Import them with an absolute path:

```python
from scripts.lora._dataset import find_images
```

---

## Checklist for adding a script

1. Create `scripts/<theme>/<script>.py`
2. Define `TITLE`, `DESCRIPTION`, and `run()` at module level
3. Put all logic in one or more typed public functions; `run()` only parses and
   dispatches
4. Add a module-level `_EXAMPLES` string with 2–4 concrete invocations (include
   all positional args so the reader can copy-paste)
5. Define `get_parser() -> ArgumentParser` that constructs and returns the parser
6. Construct the parser inside `get_parser()` using `ScriptoriumParser` (from
   `core.argparse`) with `prog="uv run main.py <theme>.<script>"`,
   `epilog=_EXAMPLES`, and `formatter_class=argparse.RawDescriptionHelpFormatter`;
   `run()` calls `get_parser().parse_args()`
7. Use `core.outputs.resolve_output()` or `core.outputs.resolve_output_dir()` for
   output paths; use `core.paths.inputs_dir("<theme>")` for input defaults; resolve
   bare filenames inside `run()` before passing to public functions
8. If the script processes user-supplied files, add `ACCEPTS: set[str]` with the
   applicable categories (see `core/categories.py`) so it appears in Drop-to-Discover
9. Verify it appears in `uv run main.py`
9. Verify `uv run main.py <theme>` lists the script with its title and description
10. Verify `uv run main.py <theme>.<script> --help` shows the correct usage line,
    arguments, and examples

---

## Checklist for adding a theme

1. Create `scripts/<theme>/` directory
2. Add `scripts/<theme>/__init__.py` with:
   - A module docstring (conventional, not used at runtime)
   - `LABEL = "..."` — display name for the web UI sidebar and CLI listings
   - `DESCRIPTION = "..."` — one-line tagline for the web UI header and `uv run main.py <theme>`
3. No theme-local `inputs/` or `outputs/` directories are needed — every theme
   shares the repo-root `inputs/` and writes to `outputs/<theme>/` automatically
4. Add a `_utils.py` (or equivalent) that delegates to `core.paths.inputs_dir()`
   and `core.paths.outputs_dir()` if the theme's scripts read from or write to
   local files
5. Verify the theme appears in `uv run main.py` (top-level listing)
6. Verify `uv run main.py <theme>` prints the description followed by the script list
7. Verify the theme appears in the web UI sidebar with the correct label and description
