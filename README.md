# Scriptorium

Themed utility scripts with a single CLI entrypoint.

## Quickstart Guide

1. Clone repo
2. Run `uv sync`

Done.

Note individual scripts' prerequisites listed below:

- `av.*` scripts require **ffmpeg** (and **ffprobe**) to be on your `PATH` for all platforms.
    - **Fix:** Install via your package manager (e.g. `winget install Gyan.FFmpeg`, `brew install ffmpeg`).

## How To Use

```sh
uv run main.py                          # list all scripts
uv run main.py <theme>.<script> --help  # usage for a specific script
uv run main.py <theme>.<script> [args]  # run it
```

## Scripts Available

| Script     | Description                     |
|------------|---------------------------------|
| av.join    | Join multiple media files into a single file |
| av.trim    | Trim media files |
| av.split   | Split media files into multiple segments |
| av.convert | Convert a media file to a target format |
| av.tag     | Read/write metadata or EXIF tags |
| av.volume  | Adjust or normalize volume, or apply fades to audio files |
| av.extract_frames | Extract evenly-spaced frames from a video |
| lora.validate | Validate a LoRA training dataset |
| lora.export_captions | Export image captions from a directory to a JSON file |
| lora.import_captions | Import image captions from a JSON file to a directory |
| lora.renumber | Renumber dataset images to sequential img_NNN naming |


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
