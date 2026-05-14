# Scriptorium

Themed utility scripts toolkit, running as platform-specific apps, a webapp with browser-based UI, or a CLI tool. Built by coders, for non-coders.

![Scriptorium Logo](webapp/static/logo.webp)


## Quickstart: Install

1. Clone repo
2. Run `uv sync`

Done.

Note individual scripts' prerequisites listed below:

1. `av.*` scripts require **ffmpeg** (and **ffprobe**) to be on your `PATH` for all platforms.
**Fix:** Install via your package manager (e.g. `winget install Gyan.FFmpeg`, `brew install ffmpeg`).

## Quickstart: Run the Web UI

```sh
uv run webapp                           # start at http://127.0.0.1:8000
```

The web UI lists all scripts grouped by theme. Clicking a script opens a detail
page with an auto-generated form. File inputs support drag-and-drop upload.
Submitting the form runs the script and streams output in real time.

## Building Apps

A single command builds the distributable app for your platform:

```sh
bash build.sh
```

The script auto-detects your OS, installs missing tools (uv, Homebrew, ffmpeg),
and runs the full build pipeline. No manual setup required.

| Platform | Output | Prerequisites |
|----------|--------|---------------|
| macOS | `dist/Scriptorium.app` | None (tools are auto-installed) |
| Windows | `dist/ScriptoriumSetup.exe` | Git Bash, [Inno Setup 6+](https://jrsoftware.org/issetup.php) on PATH |

### macOS app

Double-clicking the app starts the web server and opens a browser window.
File outputs go to `~/scriptorium/outputs/<theme>/`; uploaded inputs are saved to
`~/scriptorium/inputs/<theme>/`.

On a Mac that did not build it, clear the quarantine flag first:
`xattr -cr dist/Scriptorium.app`.

### Windows installer

The installer supports two modes: "Install for all users" (requires admin, installs
to `C:\Program Files\Scriptorium`) or "Install just for me" (no admin rights,
installs to `%LOCALAPPDATA%\Programs\Scriptorium`). It creates a Start Menu shortcut
and optionally adds the install directory to PATH for CLI usage.

### Platform-specific build scripts

The unified `build.sh` delegates to these under the hood — they can still be
invoked directly if needed:

- **macOS:** `bash packaging/build.sh`
- **Windows:** `packaging\build_installer.bat`

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
| av.volume  | Adjust audio volume, normalize, or apply fade-in/out |
| downloads.download | Download media from a URL (YouTube, Vimeo, etc.) |
| formats.convert_audio | Convert audio |
| formats.convert_image | Convert image |
| formats.convert_tabular | Convert tabular |
| formats.convert_video | Convert video |
| lora.export_captions | Export captions to JSON |
| lora.import_captions | Import captions from JSON |
| lora.renumber | Renumber LoRA dataset images |
| lora.validate | Validate a LoRA training dataset |


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

run_fn(export, Path("scripts/lora/inputs"), Path("scripts/lora/outputs/captions.json"))
```

## More Information

See [SPEC.md](SPEC.md) for the full design.
