import argparse
import sys
from pathlib import Path

from scripts.lora._dataset import IMG_NAME_RE, find_captions, find_images

TITLE = "Validate LoRA dataset"
DESCRIPTION = "Check that images follow img_NNN naming and each has a matching caption .txt file."


def validate(directory: Path) -> bool:
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


def run() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument(
        "--inputs",
        type=Path,
        default=Path(__file__).parent / "inputs",
        metavar="DIR",
        help="dataset directory (default: inputs/ next to this script)",
    )
    args = parser.parse_args()
    sys.exit(0 if validate(args.inputs) else 1)
