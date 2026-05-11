"""LoRA dataset caption export script."""

import argparse
import json
from pathlib import Path
import sys

from scripts.lora._dataset import find_captions

TITLE = "Export captions to JSON"
DESCRIPTION = "Collect all .txt caption files in the dataset and write {filename: text} as JSON."

_INPUTS_DIR = Path(__file__).parent / "inputs"
_OUTPUTS_DIR = Path(__file__).parent / "outputs"


def _resolve_output(name: str | None) -> Path | None:
    if name is None:
        return None
    stem = Path(name).stem  # tolerate 'captions' or 'captions.json'
    return _OUTPUTS_DIR / f"{stem}.json"


def export(directory: Path, output: Path | None) -> None:
    """Export caption text files in directory to a JSON file or stdout."""
    if not directory.is_dir():
        print(f"error: inputs directory not found: {directory}", file=sys.stderr)
        sys.exit(1)

    captions = find_captions(directory)
    data = {p.name: p.read_text(encoding="utf-8").strip() for p in captions}
    payload = json.dumps(data, indent=2, ensure_ascii=False)

    if output is None:
        print(payload)
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
        print(f"wrote {len(data)} caption(s) to {output}")


_EXAMPLES = """
examples:
  uv run main.py lora.export_captions
  uv run main.py lora.export_captions --output captions
  uv run main.py lora.export_captions --inputs path/to/dataset/ --output my_captions
"""


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to export()."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py lora.export_captions",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--inputs",
        type=Path,
        default=_INPUTS_DIR,
        metavar="DIR",
        help="dataset directory (default: lora/inputs/; bare name resolves to lora/inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        nargs="?",
        const="captions",
        default=None,
        metavar="NAME",
        help="write to outputs/NAME.json (default name: captions); omit flag entirely for stdout",
    )
    args = parser.parse_args()
    inputs = args.inputs
    if inputs.parent == Path("."):
        inputs = _INPUTS_DIR / inputs.name
    export(inputs, _resolve_output(args.output))
