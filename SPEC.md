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
├── core/
│   ├── argparse.py          # ScriptoriumParser with ui_label support
│   ├── config.py            # user settings persistence (UserConfig, load, save)
│   ├── paths.py             # centralized path resolution (frozen vs dev)
│   ├── registry.py          # auto-discovers scripts and themes
│   └── runner.py            # dispatch + middleware (run, run_fn)
├── scripts/
│   └── <theme>/
│       ├── __init__.py      # LABEL, DESCRIPTION; gitignored inputs/ and outputs/
│       ├── _helpers.py      # private shared code (ignored by registry)
│       ├── <script>.py      # one script per file
│       ├── inputs/          # gitignored — drop files here to process
│       └── outputs/         # gitignored — results land here
├── webapp/
│   ├── app.py               # FastAPI server
│   ├── _form.py             # argparse introspection for auto-generated forms
│   ├── static/              # CSS, logo
│   └── templates/           # Jinja2 templates (base, index, script detail)
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

`inputs/`, `outputs/`, and `past_inputs/` directories are gitignored everywhere
in the repo and are the conventional locations for local data.

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

The web UI lists all scripts grouped by theme, with live search and dark/light mode.
Clicking a script opens a detail page with an auto-generated form (built from
`get_parser()`). Path-typed arguments render as drag-and-drop file upload fields
(except `--outputs` and `--inputs` directory args, which remain text fields).
Submitting the form runs the script and streams its output via SSE.

Uploaded files are saved to the theme's inputs directory via `POST /upload/{theme}`.

When ffmpeg is not found on PATH, a banner appears in the sidebar with install
instructions.

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

| Name          | Type  | Purpose                                                             |
|---------------|-------|---------------------------------------------------------------------|
| `LABEL`       | `str` | Display name used in the web UI sidebar and CLI listings            |
| `DESCRIPTION` | `str` | One-line tagline shown below the theme name in the web UI and at the top of `uv run main.py <theme>` output |

The module docstring is conventional documentation — it is not used by the runtime.

```python
"""A/V manipulation scripts backed by ffmpeg."""

LABEL = "A/V"
DESCRIPTION = "Audio and video processing backed by ffmpeg"
```

`theme_labels()` and `theme_descriptions()` in `core/registry.py` read these
attributes at runtime. Both fall back gracefully if an attribute is absent.

---

## inputs / outputs convention

Every theme that reads or writes files uses the same layout:

```
scripts/<theme>/
    inputs/     # gitignored; drop source files here
    outputs/    # gitignored; processed results land here
```

Scripts resolve a bare filename (no directory component in the path) against the
theme's `inputs/` directory automatically, so users can type just a filename:

```sh
uv run main.py av.convert clip.mp4 --to mp3   # resolves to av/inputs/clip.mp4
```

### `core.paths` — centralized path resolution

All path resolution goes through `core.paths`, which detects whether the app is
running as a frozen PyInstaller bundle or in development:

| Mode   | `inputs_dir("av")`                | `outputs_dir("av")`                |
|--------|-----------------------------------|------------------------------------|
| Dev    | `scripts/av/inputs/`              | `scripts/av/outputs/`              |
| Frozen | `~/scriptorium/inputs/av/`        | `~/scriptorium/outputs/av/`        |

Theme helpers delegate to `core.paths`:

```python
from core.paths import inputs_dir, outputs_dir

def av_inputs_dir() -> Path:
    return inputs_dir("av")
```

`core.paths` also provides `templates_dir()`, `static_dir()`, `has_ffmpeg()`,
`read_version()`, and the `FROZEN` boolean.

---

## Script anatomy

Every file the registry picks up must expose three names at module level:

| Name          | Type       | Purpose                                      |
|---------------|------------|----------------------------------------------|
| `TITLE`       | `str`      | One-line label shown in `uv run main.py`     |
| `DESCRIPTION` | `str`      | Sentence shown in `--help` and theme listing |
| `run()`       | `Callable` | CLI entrypoint — owns argparse + `sys.exit`  |

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

This requires using `ScriptoriumParser` from `core.argparse` instead of the
stdlib `ArgumentParser`. `ScriptoriumParser` is a drop-in subclass — it
accepts the same arguments and behaves identically, except it also supports
`ui_label`. Scripts that don't need `ui_label` can continue using the
stdlib parser.

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

```
[lora.export_captions] 0.012s          # CLI label = script key
[lora.export_captions::export] 0.011s  # programmatic label = module::function
```

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
6. Construct `ArgumentParser` inside `get_parser()` with
   `prog="uv run main.py <theme>.<script>"`, `epilog=_EXAMPLES`, and
   `formatter_class=argparse.RawDescriptionHelpFormatter`; `run()` calls
   `get_parser().parse_args()`
7. Use `core.paths.inputs_dir("<theme>")` and `core.paths.outputs_dir("<theme>")`
   for default paths; resolve bare filenames inside `run()` before passing to
   public functions
8. Verify it appears in `uv run main.py`
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
3. Create `scripts/<theme>/inputs/` and `scripts/<theme>/outputs/` directories
   (they are gitignored automatically via the root `.gitignore` pattern)
4. Add a `_utils.py` (or equivalent) that delegates to `core.paths.inputs_dir()`
   and `core.paths.outputs_dir()` if the theme's scripts read from or write to
   local files
5. Verify the theme appears in `uv run main.py` (top-level listing)
6. Verify `uv run main.py <theme>` prints the description followed by the script list
7. Verify the theme appears in the web UI sidebar with the correct label and description
