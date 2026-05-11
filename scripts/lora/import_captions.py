"""LoRA dataset caption import script."""

import argparse
import json
from pathlib import Path
import re
import sys

TITLE = "Import captions from JSON"
DESCRIPTION = "Read a captions.json and write individual img_NNN.txt files to outputs/generated_captions/."

_INPUTS_DIR = Path(__file__).parent / "inputs"
_OUTPUTS_DIR = Path(__file__).parent / "outputs" / "generated_captions"
_KEY_RE = re.compile(r"^img_(\d+)\.txt$")


def _validate(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        print(f"error: expected a JSON object, got {type(raw).__name__}")
        sys.exit(1)

    issues: list[str] = []
    numbers: list[int] = []

    for key, value in raw.items():
        m = _KEY_RE.match(key)
        if not m:
            issues.append(f"  invalid key: {key!r}  (expected img_NNN.txt)")
        else:
            numbers.append(int(m.group(1)))
        if not isinstance(value, str):
            issues.append(f"  invalid value for {key!r}: expected string, got {type(value).__name__}")

    if issues:
        print(f"error: {len(issues)} validation issue(s):")
        for issue in issues:
            print(issue)
        sys.exit(1)

    if numbers:
        numbers.sort()
        full_range = list(range(numbers[0], numbers[-1] + 1))
        if numbers != full_range:
            missing = sorted(set(full_range) - set(numbers))
            w = max(3, len(str(numbers[-1])))
            names = ", ".join(f"img_{n:0{w}d}.txt" for n in missing)
            print(f"error: non-consecutive numbering — missing: {names}")
            sys.exit(1)

    return raw  # type: ignore[return-value]


def import_captions(source: Path, output_dir: Path) -> None:
    """Import captions from a JSON file into a dataset directory as .txt files."""
    if not source.is_file():
        print(f"error: captions file not found: {source}")
        sys.exit(1)

    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: malformed JSON: {exc}")
        sys.exit(1)

    data = _validate(raw)

    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, text in data.items():
        (output_dir / filename).write_text(text, encoding="utf-8")

    print(f"wrote {len(data)} caption file(s) to {output_dir}")


_EXAMPLES = """
examples:
  uv run main.py lora.import_captions
  uv run main.py lora.import_captions --input path/to/captions.json
"""


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to import_captions()."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py lora.import_captions",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=_INPUTS_DIR / "captions.json",
        metavar="FILE",
        help="source JSON file (default: inputs/captions.json)",
    )
    args = parser.parse_args()
    import_captions(args.input, _OUTPUTS_DIR)
