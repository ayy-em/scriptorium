# Scriptorium

Themed utility toolkit, running as platform-native apps, a webapp with browser-based UI, or a CLI tool. 
Built by coders, for non-coders.

<p align="center">
  <img src="https://github.com/ayy-em/scriptorium/raw/main/webapp/static/logo.webp?raw=true" alt="Scriptorium logo"/>
</p>

## Quickstart: Install

Needs Python 3.14 and [uv](https://docs.astral.sh/uv/).

1. Clone repo
2. Run `uv sync --all-extras`

Done. Plain `uv sync` installs only the core and the web UI; each theme's
libraries (Pillow, pandas, weasyprint, rembg, …) live in an optional extra
named after it, so `--all-extras` is what you want unless you are deliberately
keeping the environment small.

### Prereqs for individual scripts

Some scripts need tools Python cannot install. Each is detected and, when
missing, named in the sidebar and on the page of every script that needs it,
with an **Install** button where one command does the job (winget on Windows,
brew on macOS) and the command to run otherwise. The first-run tour ends on an
ffmpeg slide if it is missing. The full table is under
[What the built app needs to run](#what-the-built-app-needs-to-run).

1. `av.*` and `formats.convert_{audio,video}` require **ffmpeg** (and **ffprobe**) on `PATH`.
   `winget install Gyan.FFmpeg` / `brew install ffmpeg`, or click Install.
2. `formats.convert_docs` requires **pandoc**. Same story.
3. `speech.transcribe` needs an OpenAI API key — paste it under **Settings → Keys**.

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

While a script runs, the status strip shows real progress wherever the script
reports it — position within a transcode, files done in a batch, bytes of a
model download — and an indeterminate bar otherwise. When the run finishes, the
files it wrote are listed under the console with a button to reveal each one.

**Favourites** — click the heart on any script row to pin it. The sidebar's
Favourites view shows just those, with a live count. **Sort** cycles the category
order between A → Z, Z → A and most-scripts-first. Both are stored in
`~/scriptorium/config.json`, so every way of opening the app sees the same set.

### Settings

The gear in the top bar opens Settings: light or dark theme, what the window's
close button does in the desktop app (quit, or minimise to the tray), a default
outputs directory, and **Keys** — a masked field per API key the app knows
about. A key is written to `~/scriptorium/.env`, applies at once, and is never
shown again; the field just reports *Set* or *Not set*.

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
single file run once per file, in sequence; the card says how many runs that
will be, and one failure does not stop the rest.

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

| Platform | Output | Prerequisites to *build* |
|----------|--------|---------------|
| macOS | `dist/Scriptorium.app` (CI also wraps it in `Scriptorium-macOS.dmg`) | None (tools are auto-installed) |
| Windows | `dist/ScriptoriumSetup.exe` | [Inno Setup 6+](https://jrsoftware.org/issetup.php) on PATH; `build.bat` is plain cmd, Git Bash only if you prefer `bash build.sh` |
| Linux | `dist/scriptorium-linux-x86_64.tar.gz` | None (tools are auto-installed) |

### What the built app needs to run

The table above covers building. A packaged app on someone *else's* machine is
a different question — the bundle carries its Python dependencies but not the
heavy native ones, and every script still works without them except the ones
listed here.

Each of these is **detected**, and any that is missing is named in the sidebar
and at the top of every script page that needs it. Where one unattended command
does the job (winget on Windows, brew on macOS) there is an **Install** button
that runs it for you and shows the installer's output; a key gets a **Set key**
button that opens Settings; otherwise you get the command to run. The check
re-runs as you use the app, so installing something and reloading the page
clears it without a restart.

| Needed for | Requirement | Without it |
|---|---|---|
| `av.*`, `formats.convert_{audio,video}` | **ffmpeg** and **ffprobe** on `PATH` | Those scripts fail; everything else is unaffected |
| `formats.convert_docs` | **pandoc** on `PATH` | Document conversion fails |
| Telegram PDF reports | **pango, cairo, glib** — Homebrew on macOS, MSYS2 or the GTK3 runtime on Windows | PDF output fails; the other Telegram scripts are unaffected |
| `speech.transcribe` | An OpenAI API key — paste it under **Settings → Keys** (stored in `~/scriptorium/.env`), or set `OPENAI_API_KEY` in a `.env` file | The script errors out |
| `photo.remove_bg` | Model weights, ~170MB per model (~215MB for the `hq` preset's `birefnet-general-lite`, ~950MB for `birefnet-general`) | Downloaded to `~/.u2net/` on first use of each model; the form says so before you run, and the status bar shows the download |

Two more are optional — reported, but nothing breaks without them: **gifsicle**
makes `av.to_anim --optimize` more effective, and the **weasyprint** CLI gives
`formats.convert_docs` nicer PDFs than pandoc's own engine.

Windows additionally needs **Edge or Chrome** for the desktop window; the
installer will not check for it.

`gif.make_gif` needs nothing external despite sitting next to the A/V scripts —
it assembles frames with Pillow.

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

### Using the packaged app from anywhere

The desktop build ships a console binary alongside the windowed one, so you can
use Scriptorium as an ordinary command-line tool. Put it on your `PATH`:

```sh
# macOS
ln -s /Applications/Scriptorium.app/Contents/MacOS/scriptorium ~/.local/bin/scriptorium

# Linux — from the extracted tarball
ln -s "$PWD/scriptorium/scriptorium" ~/.local/bin/scriptorium
```

On Windows the installer offers **Add to PATH** during setup; tick it and
`scriptorium` works in any new terminal.

It then behaves like any other CLI tool — relative paths are relative to where
you are standing, and results are written beside them:

```sh
cd ~/Movies/holiday
scriptorium av.trim thing.mp4 00:12 01:07   # reads ./thing.mp4, writes ./<stamp>.mp4
```

Run it with no source argument and it falls back to the shared `inputs/` folder
instead, which is what the web UI uses. Pass `--output` at any time to be
explicit.

### What happens to your input file

A script that consumes a file moves it to `inputs/processed/` once it has
finished with it, so the inputs folder shows what is still waiting to be done.

**This only ever applies to files inside `inputs/`.** Point a script at
`~/Movies/holiday.mp4` and it is read and left exactly where it is — nothing is
moved, and no `processed/` folder appears next to your media. If a file of the
same name is already archived, the new one gets a timestamp suffix rather than
overwriting it.

A few scripts deliberately do not archive: the `lora.*` tools work on a dataset
folder in place, the `telegram.*` chain needs its export again at the next step,
and `gif.make_gif` reads a folder of frames you will likely re-render at other
settings.

## Scripts Available

27 scripts across 9 categories. Titles are the scripts' own `TITLE` values.

| Script | What it does |
|--------|--------------|
| `av.dump_frames` | Dump all frames from a video clip |
| `av.filmstrip` | Video filmstrip sheet |
| `av.join` | Join multiple media files |
| `av.split` | Split media file in multiple segments |
| `av.tag` | Read/write media metadata tags |
| `av.to_anim` | Turn a video segment into an animated GIF/WebP |
| `av.trim` | Trim the media file that's just too damn long |
| `av.video_crop` | Crop a video by trimming its edges |
| `av.volume` | Adjust audio volume, normalize, or apply fade-in/out |
| `downloads.download` | Download media from a URL (YouTube, Vimeo, etc.) |
| `formats.convert_audio` | Convert audio |
| `formats.convert_docs` | Convert documents |
| `formats.convert_image` | Convert image (HEIC/HEIF in, PNG/JPEG/WebP out) |
| `formats.convert_tabular` | Tabular Data: .csv, .json, .xlsx, .ods, .tsv |
| `formats.convert_video` | Convert video |
| `gif.make_gif` | Make a gif |
| `lora.export_captions` | Export captions to JSON |
| `lora.import_captions` | Import captions from JSON |
| `lora.renumber` | Renumber LoRA dataset images |
| `lora.validate` | Validate a LoRA training dataset |
| `photo.remove_bg` | Remove background |
| `sitemaps.status_check` | Sitemap Status Check |
| `speech.transcribe` | Transcribe audio to text |
| `telegram.chat_analysis` | Analyze your Telegram chat history and generate a report full of insights |
| `telegram.embed_messages` | Embed preprocessed Telegram messages |
| `telegram.group_analysis` | Analyze a Telegram group chat and generate a visual analytics report |
| `telegram.preprocess` | Preprocess Telegram export for embeddings |


## How To Use: CLI Examples

```sh
# Get help for a script
uv run main.py av.join --help

# Trim a video to a time range
uv run main.py av.trim input.mp4 00:00:05 00:01:30

# Skip the first 30 seconds, keep the rest
uv run main.py av.trim input.mp4 30

# Name the output yourself
uv run main.py av.trim input.mp4 1:03 5:04 --output cut.mp4

# Accept a keyframe-snapped cut rather than re-encoding for an exact one
uv run main.py av.trim input.mp4 00:03 --mode fast

# Remove a background with the default preset, or the slow high-quality one
uv run main.py photo.remove_bg portrait.heic
uv run main.py photo.remove_bg portrait.jpg --preset hq

# Not sure which model suits the photo? Run all three and compare the outputs
uv run main.py photo.remove_bg photos/ --all-presets
```

`photo.remove_bg` presets are named for cost, not quality — `fast` (u2net),
`balanced` (isnet-general-use with mask clean-up) and `hq` (birefnet-general-lite
with alpha matting) — because no model wins on every image. `--all-presets`
writes `fast_…`, `balanced_…` and `hq_…` side by side so you can pick by eye.

`av.trim` cuts where you asked. A stream copy can only start at a keyframe, so
when the nearest one is not close enough to your start time, the video is
re-encoded instead of quietly rounding the cut backwards — which on a
low-frame-rate or long-GOP source used to mean getting most of the original
file back and being told it worked. `--mode fast` opts out and keeps the copy.

## How To Use: Programmatic Examples

```python
from scripts.lora.export_captions import export
from core.runner import run_fn
from pathlib import Path

run_fn(export, Path("inputs"), Path("outputs/lora/captions.json"))
```

## Version History

### Unreleased
- **Install missing dependencies from the app** — ffmpeg and pandoc get an Install button in the sidebar, on the script pages that need them, and on a first-run tour slide; winget or brew runs with output streamed into the UI, no restart needed
- **`photo.remove_bg` presets** — `--quality` is now `--preset fast|balanced|hq`, named for cost rather than quality because no model wins on every image; `--all-presets` runs all three over the same inputs for side-by-side comparison
- **Model downloads are visible** — the form says which weights a run will fetch and how big they are; the status bar shows the download instead of a run that looks hung
- **`av.join` respects the output container** — WebM output gets Opus audio, a copied codec the container cannot hold forces a re-encode, and a re-encode that WebM cannot hold is written as MP4 with a note
- **API keys in Settings** — paste the OpenAI key under Settings → Keys instead of editing a `.env` file; it is stored per user, never shown again, and the sidebar clears at once
- **HEIC in, PNG/JPEG out** — `formats.convert_image` and `photo.remove_bg` read iPhone and Android HEIC/HEIF photos; a Live Photo converts to its still frame, and EXIF orientation is baked in so portraits stay upright
- **`av.trim` plays a dropped file** — the play button now works for a file that arrived through the drop overlay, not only one picked on the page
- **UI** — thin scrollbars that appear only while scrolling, more contrast between dark-mode surfaces, search icon no longer overlaps its placeholder, the shortcut badge reads Ctrl K off macOS, and static assets revalidate so a new build never shows an old stylesheet

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
