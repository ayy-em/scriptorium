"""LoRA dataset validation script."""

import argparse
from pathlib import Path
import sys

from scripts.lora._dataset import IMG_NAME_RE, find_captions, find_images

TITLE = "Validate LoRA dataset"
_INPUTS_DIR = Path(__file__).parent / "inputs"
DESCRIPTION = "Check that images follow img_NNN naming and each has a matching caption .txt file."


def validate(directory: Path) -> bool:
    """Validate images and captions in a LoRA dataset directory."""
    if not directory.is_dir():
        print(f"error: inputs directory not found: {directory}", file=sys.stderr)
        return False

    images = find_images(directory)
    captions = find_captions(directory)
    issues: list[str] = []

    for img in images:
        if not IMG_NAME_RE.match(img.stem):
            issues.append(f"  bad name:        {img.name}  (expected img_NNN.ext)")

    image_stems = {img.stem for img in images}

    for img in images:
        if not (directory / f"{img.stem}.txt").exists():
            issues.append(f"  missing caption: {img.name}")

    for cap in captions:
        if cap.stem not in image_stems:
            issues.append(f"  orphan caption:  {cap.name}")

    print(f"images:   {len(images)}")
    print(f"captions: {len(captions)}")

    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            print(issue)
        return False

    print("\ndataset valid.")
    return True


_EXAMPLES = """
examples:
  uv run main.py lora.validate
  uv run main.py lora.validate --inputs path/to/dataset/
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py lora.validate",
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
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to validate()."""
    args = get_parser().parse_args()
    inputs = args.inputs
    if inputs.parent == Path("."):
        inputs = _INPUTS_DIR / inputs.name
    sys.exit(0 if validate(inputs) else 1)
