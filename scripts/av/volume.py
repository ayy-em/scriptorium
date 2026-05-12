"""CLI and programmatic interface for adjusting audio volume."""

import argparse
from pathlib import Path
import sys

from scripts.av._utils import av_inputs_dir, av_outputs_dir, probe_streams, run_ffmpeg, run_ffprobe

TITLE = "Adjust audio volume, normalize, or apply fade-in/out"
DESCRIPTION = "Apply composable volume operations in a single ffmpeg pass: amplify -> normalize -> fade-in -> fade-out."


def adjust_volume(  # noqa: PLR0913
    input: Path,
    output: Path,
    *,
    normalize: bool = False,
    amplify_db: float | None = None,
    fade_in: float | None = None,
    fade_out: float | None = None,
) -> None:
    """Apply audio volume filters to a media file in a single ffmpeg pass.

    Filters are applied in this fixed order regardless of argument order:
      1. amplify   (volume=<n>dB)
      2. normalize (loudnorm — single-pass EBU R128)
      3. fade-in   (afade=t=in)
      4. fade-out  (afade=t=out)

    When normalize is True, a note is printed to stdout after the run
    suggesting a second pass for optimal loudnorm accuracy.

    Args:
        input: Source media file.
        output: Destination file path.
        normalize: Apply EBU R128 loudnorm (single-pass).
        amplify_db: Boost or cut volume by N dB (negative values reduce volume).
        fade_in: Apply a fade-in of N seconds at the start.
        fade_out: Apply a fade-out of N seconds at the end.

    Raises:
        ValueError: If no audio operations are specified.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    if not normalize and amplify_db is None and fade_in is None and fade_out is None:
        raise ValueError("At least one audio operation must be specified")

    filters: list[str] = []

    if amplify_db is not None:
        filters.append(f"volume={amplify_db}dB")
    if normalize:
        filters.append("loudnorm")
    if fade_in is not None:
        filters.append(f"afade=t=in:d={fade_in}")
    if fade_out is not None:
        duration = _get_duration(input)
        start = max(0.0, duration - fade_out)
        filters.append(f"afade=t=out:st={start:.3f}:d={fade_out}")

    af_chain = ",".join(filters)
    run_ffmpeg(["-i", str(input), "-af", af_chain, str(output)])

    if normalize:
        print(
            "Note: loudnorm is most accurate in two passes. "
            "For optimal results, run 'av.volume --normalize' again on the output."
        )


def _get_duration(file: Path) -> float:
    """Return the duration in seconds of the audio content in a media file.

    Falls back to format-level duration if no audio stream duration is found.

    Args:
        file: Media file to probe.

    Returns:
        Duration in seconds.

    Raises:
        ValueError: If duration cannot be determined.
    """
    streams = probe_streams(file)
    for stream in streams:
        if stream.get("codec_type") == "audio" and "duration" in stream:
            return float(stream["duration"])

    data = run_ffprobe(["-show_format", str(file)])
    duration = data.get("format", {}).get("duration")
    if duration is None:
        raise ValueError(f"Cannot determine duration of {file}")
    return float(duration)


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py av.volume",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Filter order (always applied in this sequence, regardless of flag order):\n"
            "  1. --amplify\n"
            "  2. --normalize\n"
            "  3. --fade-in\n"
            "  4. --fade-out\n"
            "\n"
            "examples:\n"
            "  uv run main.py av.volume input.mp3 output.mp3 --amplify 3\n"
            "  uv run main.py av.volume input.mp3 --normalize --fade-in 2 --fade-out 3\n"
            "  uv run main.py av.volume input.mp4 output.mp4 --amplify -6 --fade-out 5"
        ),
    )
    parser.add_argument("input", type=Path, help="Source media file (bare name resolves to av/inputs/)")
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=None,
        help="Destination file (default: av/outputs/<input_name>)",
    )
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Apply EBU R128 loudnorm (single-pass; see epilog for two-pass tip)",
    )
    parser.add_argument(
        "--amplify",
        type=float,
        metavar="DB",
        dest="amplify_db",
        help="Amplify by N dB (negative to reduce)",
    )
    parser.add_argument("--fade-in", type=float, metavar="S", dest="fade_in", help="Fade-in duration in seconds")
    parser.add_argument("--fade-out", type=float, metavar="S", dest="fade_out", help="Fade-out duration in seconds")
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to adjust_volume()."""
    args = get_parser().parse_args()

    input_file = args.input
    if input_file.parent == Path("."):
        input_file = av_inputs_dir() / input_file.name

    output = args.output or (av_outputs_dir() / input_file.name)

    try:
        adjust_volume(
            input_file,
            output,
            normalize=args.normalize,
            amplify_db=args.amplify_db,
            fade_in=args.fade_in,
            fade_out=args.fade_out,
        )
        print(f"Written: {output}")
        sys.exit(0)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
