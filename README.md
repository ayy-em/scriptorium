# Scriptorium

Themed utility scripts with a single CLI entrypoint.

## Setup

```sh
uv sync
```

## Usage

```sh
uv run main.py                          # list all scripts
uv run main.py <theme>.<script> --help  # usage for a specific script
uv run main.py <theme>.<script> [args]  # run it
```

## Examples

```sh
# Validate a LoRA training dataset in scripts/lora/inputs/
uv run main.py lora.validate

# Export all captions to scripts/lora/outputs/captions.json
uv run main.py lora.export_captions --output

# Export to a custom filename
uv run main.py lora.export_captions -o my_run

# Preview renaming images to sequential img_NNN naming
uv run main.py lora.renumber

# Trim a video to a time range
uv run main.py av.trim input.mp4 output.mp4 --start 00:00:05 --end 00:01:30
```

## Programmatic use

```python
from scripts.lora.export_captions import export
from core.runner import run_fn
from pathlib import Path

run_fn(export, Path("scripts/lora/inputs"), Path("scripts/lora/outputs/captions.json"))
```

See [SPEC.md](SPEC.md) for the full design.
