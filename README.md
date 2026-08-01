# Scriptorium

Themed utility toolkit, running as platform-native apps, a webapp with browser-based UI, or a CLI tool. 
Built by coders, for non-coders.

<p align="center">
  <img src="https://github.com/ayy-em/scriptorium/raw/main/webapp/static/logo.webp?raw=true" alt="Scriptorium logo"/>
</p>

## Quickstart: Install

1. Clone repo
2. Run `uv sync`

Done.

### Prereqs for individual scripts

1. `av.*` scripts require **ffmpeg** (and **ffprobe**) to be on your `PATH` for all platforms.
**Fix:** Install via your package manager (e.g. `winget install Gyan.FFmpeg`, `brew install ffmpeg`).

## Quickstart: Run the Web UI

```sh
uv run webapp                           # start at http://127.0.0.1:8000
```

The web UI lists all scripts grouped by theme. Clicking a script opens a detail
page with an auto-generated form. File inputs support drag-and-drop upload.
Submitting the form runs the script and streams output in real time into a
console panel with timestamps, colour-coded severities and auto-scroll.

A context column beside the form shows what the script accepts, what each field
means, and a live summary of the settings you have chosen.

**Preview command** turns the current form state into the exact CLI invocation,
ready to copy:

```sh
uv run main.py av.filmstrip inputs/sample-video.mp4 --grid 2x5 --format pdf
```

It is generated server-side from the same code that builds the real run, so it
cannot drift from what actually executes.

Inputs that accept either a file or a whole directory show a **Files / Folder**
toggle above the picker. Both modes upload into one batch directory and hand the
script that directory's path.

Fonts and the JS runtime are served locally, so the UI works with no internet
connection. Light and dark themes are both fully supported; switch from the top
bar or in Settings.

**Favourites** — click the heart on any script row to pin it. The sidebar's
Favourites view shows just those, with a live count. **Sort** cycles the category
order between A → Z, Z → A and most-scripts-first. Both are remembered per
browser profile; the three launch tiers each keep their own set (see
[BACKLOG.md](BACKLOG.md)).

### Cancelling and re-running

**Cancel** appears next to the status strip while a script is running. It kills
the whole process tree, not just the Python parent — so the ffmpeg or yt-dlp
doing the actual work stops too, rather than carrying on invisibly. Whatever the
run already wrote to disk is left alone.

**History** records every run at `~/scriptorium/history.json` — script,
arguments, outcome, duration — newest first, capped at 200. Open it from the
sidebar. **Re-run** takes you back to the script's form with the original
arguments filled in, so you can adjust something before running it again.

### Drop to discover

Drag a file onto the main screen and the script list is replaced by a chooser:
the file appears on the left and every script that can process it fans out on an
arc to the right. Seven cards are visible at a time; when more match, rotate the
wheel with the mouse wheel, by dragging, with the arrow keys, or via the arrow
buttons. Tab reaches every card regardless of rotation.

Picking a card either opens the script's own page (for scripts with a custom
editor, such as `av.trim`) or expands into an inline form that runs the script
without leaving the page.

You can also **paste an image straight from the clipboard** — copy an image
anywhere, focus Scriptorium, press <kbd>Ctrl</kbd>+<kbd>V</kbd>, and it is saved
to `inputs/drop/<session>/` under a generated name and staged for use.

**Batches.** Dropping several files at once works as long as they are all the
same kind — `.mp4` alongside `.mov` is fine, `.docx` alongside `.avi` is
rejected. Scripts that accept a directory (`av.join`, the `formats.convert_*`
family, `photo.remove_bg`) run once over the whole batch. Scripts that take a
single file are shown dimmed and marked *single file only*; running those across
a batch is tracked in [BACKLOG.md](BACKLOG.md).

## Building Apps

A single command builds the distributable app for your platform:

Mac:
```sh
bash build.sh
```

Windows:
```bash
build
```

The script auto-detects your OS, installs missing tools (uv, Homebrew, ffmpeg),
and runs the full build pipeline. No manual setup required.

| Platform | Output | Prerequisites |
|----------|--------|---------------|
| macOS | `dist/Scriptorium.app` | None (tools are auto-installed) |
| Windows | `dist/ScriptoriumSetup.exe` | Git Bash, [Inno Setup 6+](https://jrsoftware.org/issetup.php) on PATH |
| Linux | `dist/scriptorium-linux-x86_64.tar.gz` | None (tools are auto-installed) |

### macOS app

Double-clicking the app starts the web server and opens a native window
(WKWebView), falling back to a Chromium `--app` window and then the default
browser if that is unavailable.

File outputs go to `~/scriptorium/outputs/<theme>/`; uploaded inputs are saved to
the shared `~/scriptorium/inputs/` folder.

Run the binary inside the bundle directly for CLI access — with a script key to
run one, or bare to list them all:

```sh
dist/Scriptorium.app/Contents/MacOS/scriptorium av.trim input.mp4 00:10
```

On a Mac that did not build it, clear the quarantine flag first:
`xattr -cr dist/Scriptorium.app`.

### Windows installer

The installer supports two modes: "Install for all users" (requires admin, installs
to `C:\Program Files\Scriptorium`) or "Install just for me" (no admin rights,
installs to `%LOCALAPPDATA%\Programs\Scriptorium`). It creates a Start Menu shortcut
and optionally adds the install directory to PATH for CLI usage.

### Linux binary

Extract the tarball and run the `scriptorium` binary. The app opens a Chromium
`--app` window if Chrome/Chromium is installed, otherwise falls back to the
default browser with a Quit button in the sidebar.

### Platform-specific build scripts

The unified `build.sh` delegates to these under the hood — they can still be
invoked directly if needed:

- **macOS:** `bash packaging/build.sh`
- **Windows:** `packaging\build_installer.bat`
- **Linux:** `bash packaging/build_linux.sh`

### CI / Releases

Pushing a version tag (e.g. `v0.4.0`) triggers the GitHub Actions workflow at
`.github/workflows/release.yml`, which builds all three platform artifacts and
attaches them to a GitHub Release.

## How To Use: CLI

```sh
uv run main.py                          # list all scripts
uv run main.py <theme>.<script> --help  # usage for a specific script
uv run main.py <theme>.<script> [args]  # run it
```

## Scripts Available

| Script     | Description                     |
|------------|---------------------------------|
| av.dump_frames | Dump all frames from a video clip |
| av.filmstrip | Video filmstrip sheet |
| av.join    | Join multiple media files |
| av.split   | Split media file in multiple segments |
| av.tag     | Read/write media metadata tags |
| av.to_anim | Turn a video segment into an animated GIF/WebP |
| av.trim    | Trim a media file |
| av.video_crop | Crop a video by trimming its edges |
| av.volume  | Adjust audio volume, normalize, or apply fade-in/out |
| downloads.download | Download media from a URL (YouTube, Vimeo, etc.) |
| formats.convert_audio | Convert audio |
| formats.convert_image | Convert image |
| formats.convert_tabular | Convert tabular |
| formats.convert_video | Convert video |
| sitemaps.status_check | Check HTTP status and response times for every URL in a sitemap |
| lora.export_captions | Export captions to JSON |
| lora.import_captions | Import captions from JSON |
| lora.renumber | Renumber LoRA dataset images |
| lora.validate | Validate a LoRA training dataset |
| telegram.chat_analysis | Generate a descriptive-analytics report (JSON + PDF + charts) from a Telegram personal-chat export |


## How To Use: CLI Examples

```sh
# Get help for a script
uv run main.py av.join --help

# Trim a video to a time range
uv run main.py av.trim input.mp4 output.mp4 --start 00:00:05 --end 00:01:30

# Trim the first 30 seconds
uv run main.py av.trim input.mp4 output.mp4 --seconds 30
```

## How To Use: Programmatic Examples

```python
from scripts.lora.export_captions import export
from core.runner import run_fn
from pathlib import Path

run_fn(export, Path("inputs"), Path("outputs/lora/captions.json"))
```

## Version History

### v0.5.3
- **Background removal works in the packaged app** — `photo.remove_bg` failed to start in every built release; two separate packaging faults, both now guarded by tests
- **One tray icon** — Windows launched with two, the first of them dead
- **Drop-to-Discover fixed** — choosing a script from the wheel now takes you to the form instead of stranding you on an oversized page
- **New logo set** — vector logo across splash, top bar and favicon, with cut-to-size rasters for the tray and installers

### v0.5.2
- **Run control** — Cancel a running script and it stops the whole process tree, so ffmpeg and yt-dlp die with it instead of carrying on invisibly
- **History & re-run** — every run is recorded; the History view lists them and Re-run reopens the form with the original arguments
- **Favourites & sort** — star scripts into their own view, and cycle category order between A→Z, Z→A and most-scripts-first
- **UI overhaul** — redesigned settings modal, two-column script page with a live CLI command preview, timestamped terminal output, boot splash, and a full light/dark token set
- **Works offline** — fonts and Alpine.js are now self-hosted, so the packaged app no longer depends on a CDN
- Plus the Drop-to-Discover wheel, the `av.trim` waveform editor, `scriptorium.exe` CLI mode, and `av.join` loudness normalisation, all previously unreleased

### v0.5.1
- **Standardized output paths** — all scripts use a unified `--output` flag with `YYYYMMDD_HHmm.ext` default naming and `_001`–`_999` collision avoidance
- **Console flickering fix** — windowed app no longer flashes cmd.exe windows when running subprocess-heavy scripts
- **Freeform filmstrip grid** — `av.filmstrip` now accepts any `ROWSxCOLS` input (e.g. `2x5`, `4x4`)
- **Webapp** — "Open outputs folder" button in topnav

### v0.5.0
- **Telegram analysis suite** — group analysis with PDF report, chat analysis with neon infographic, embeddings pipeline
- **New scripts** — gif.make_gif, av.video_crop, sitemaps.status_check, formats.convert_docs, speech.transcribe, util.notify, util.cleanup
- **ScriptoriumParser** — mandatory parser with startup arg banner for all scripts; HIDDEN flag to exclude categories from the UI
- **Quality of life** — first-visit onboarding modal, auto-archive processed inputs, persistent run logger, monoline theme icons

### v0.4.0
- **User Settings** — new settings modal with theme and output directory persistence
- **Modernized UI** — OKLch palette, refined dark mode, custom form labels, streaming output banners
- **Smarter desktop app** — auto-update check, sidebar Quit button, cross-platform Chromium `--app` window
- **Linux support** — build script, PyInstaller spec, and tarball output
- **CI/CD** — GitHub Actions release workflow builds all three platforms on tag push

### v0.3.0
- Windows installer (.exe) via PyInstaller + Inno Setup
- Unified cross-platform `build.sh` entrypoint
- Desktop app with 3-tier window cascade (pywebview, Edge --app, browser)

## More Information

See [SPEC.md](SPEC.md) for the full design.
