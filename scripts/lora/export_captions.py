import argparse
import json
import sys
from pathlib import Path

from scripts.lora._dataset import find_captions

TITLE = "Export captions to JSON"
DESCRIPTION = "Collect all .txt caption files in the dataset and write {filename: text} as JSON."

_OUTPUTS_DIR = Path(__file__).parent / "outputs"


def _resolve_output(name: str | None) -> Path | None:
    if name is None:
        return None
    stem = Path(name).stem  # tolerate 'captions' or 'captions.json'
    return _OUTPUTS_DIR / f"{stem}.json"


def export(directory: Path, output: Path | None) -> None:
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


def run() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path(__file__).parent / "inputs",
        metavar="DIR",
        help="dataset directory (default: inputs/ next to this script)",
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
    export(args.inputs, _resolve_output(args.output))
