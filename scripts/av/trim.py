import argparse
import subprocess
from pathlib import Path

TITLE = "Trim media file"
DESCRIPTION = "Cut a video or audio file to a start/end timestamp via ffmpeg."


def run() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("input", type=Path, help="Source file")
    parser.add_argument("output", type=Path, help="Destination file")
    parser.add_argument("--start", default="0", metavar="TIME", help="Start time (HH:MM:SS or seconds)")
    parser.add_argument("--end", required=True, metavar="TIME", help="End time (HH:MM:SS or seconds)")
    args = parser.parse_args()

    subprocess.run(
        ["ffmpeg", "-i", str(args.input), "-ss", args.start, "-to", args.end, "-c", "copy", str(args.output)],
        check=True,
    )
