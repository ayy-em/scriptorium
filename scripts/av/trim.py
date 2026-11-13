"""CLI and programmatic interface for trimming media files."""

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

from core.argparse import ScriptoriumParser
from core.outputs import resolve_output
from core.paths import move_to_past_inputs, resolve_input
from core.progress import ProgressReporter
from scripts.av._utils import (
    KEYFRAME_TOLERANCE,
    copy_would_land_on,
    format_time,
    has_video_stream,
    keyframe_after,
    parse_time,
    probe_duration_or_none,
    probe_streams,
    run_ffmpeg,
    run_ffmpeg_stderr,
    run_ffmpeg_with_progress,
)

TITLE = "Trim the media file that's just too damn long"
DESCRIPTION = "Cut a video or audio file by skipping ahead to a start point, optionally stopping at an end point."
ACCEPTS: set[str] = {"video", "audio"}
TEMPLATE = "scripts/av/trim.html"

# What to do when the requested start does not fall on a keyframe.
MODE_AUTO = "auto"
MODE_FAST = "fast"
MODE_PRECISE = "precise"
TRIM_MODES = (MODE_AUTO, MODE_FAST, MODE_PRECISE)

# Quality of the re-encode, on the scale ffmpeg's encoders share. 18 is
# visually lossless for x264 and matches what formats.convert_video calls
# "high" — a trim should not be the step that costs you quality you notice.
_REENCODE_CRF = "18"

# What trim() reports having done.
STRATEGY_COPY = "copy"
STRATEGY_REENCODE = "reencode"
STRATEGY_SMART = "smart"

# Source codecs a smart cut can splice: the encoder that re-creates the head,
# and the bitstream filter that puts parameter sets in-band so the copied tail
# does not depend on the head's. Anything else gets a full re-encode.
_SMART_CUT_CODECS = {
    "h264": ("libx264", "h264_mp4toannexb"),
    "hevc": ("libx265", "hevc_mp4toannexb"),
}

# How far a smart cut's duration may stray from the requested one before it is
# distrusted. A copied tail ends on a packet boundary, which can add a frame or
# two; anything beyond that means the splice went wrong.
_SMART_CUT_DURATION_SLACK = 0.25


def _should_reencode(input: Path, start_seconds: float, mode: str) -> tuple[bool, float | None]:
    """Decide whether this cut needs a re-encode to land where the user asked.

    Args:
        input: Source media file.
        start_seconds: Requested start position in seconds.
        mode: One of ``TRIM_MODES``.

    Returns:
        ``(reencode, keyframe)`` — whether to re-encode, and where a stream copy
        would have started (None when that is unknown or irrelevant).

    Raises:
        ValueError: If *mode* is not a recognised trim mode.
    """
    if mode not in TRIM_MODES:
        raise ValueError(f"Unknown trim mode {mode!r}. Choose from: {', '.join(TRIM_MODES)}")
    if mode == MODE_FAST:
        return False, None
    if mode == MODE_PRECISE:
        return True, None
    accurate, keyframe = copy_would_land_on(input, start_seconds)
    return not accurate, keyframe


def _plan_smart_cut(input: Path, start_seconds: float, end_seconds: float | None) -> tuple[dict, bool, float] | str:
    """Check whether a smart cut is possible and find where the copy can take over.

    Args:
        input: Source media file.
        start_seconds: Requested start position in seconds.
        end_seconds: Requested end position in seconds, or None for end of file.

    Returns:
        ``(video_stream, has_audio, keyframe)`` when it is, or a short reason
        when it is not.
    """
    try:
        streams = probe_streams(input)
    except Exception:
        return "the source could not be probed"
    video = next((st for st in streams if st.get("codec_type") == "video"), None)
    codec = None if video is None else video.get("codec_name")
    if codec not in _SMART_CUT_CODECS:
        return f"{codec or 'this'} video cannot be spliced"
    keyframe = keyframe_after(input, start_seconds)
    if keyframe is None:
        return "no keyframe follows the start"
    if end_seconds is not None and keyframe >= end_seconds - KEYFRAME_TOLERANCE:
        return "the cut ends before the next keyframe"
    return video, any(st.get("codec_type") == "audio" for st in streams), keyframe


def _smart_cut(input: Path, output: Path, start_seconds: float, end_seconds: float | None) -> str | None:
    """Re-encode only up to the next keyframe and stream-copy the rest.

    A full re-encode is exact but slow and costs quality over the whole range;
    a stream copy is lossless but can only begin on a keyframe. Most of a cut
    lies after the first keyframe past the start, so only the stretch before it
    needs encoding: the head is re-encoded from the exact start to that
    keyframe in the source's own codec, the tail is copied from it, and the
    audio, which has no GOP to round to, is copied whole and muxed over both.

    Splicing a re-encoded head onto copied frames is fragile: the two halves
    carry different parameter sets. They are put in-band so a decoder can
    switch at the seam, and the result is decoded once before it is accepted.
    Any failure, at any step, returns a reason and leaves nothing at *output*,
    so the caller falls back to a full re-encode rather than delivering a file
    that might not play.

    Args:
        input: Source media file.
        output: Destination file path.
        start_seconds: Requested start position in seconds.
        end_seconds: Requested end position in seconds, or None for end of file.

    Returns:
        None on success, or a short reason the smart cut was not possible.
    """
    plan = _plan_smart_cut(input, start_seconds, end_seconds)
    if isinstance(plan, str):
        return plan
    video, has_audio, keyframe = plan
    encoder, bsf = _SMART_CUT_CODECS[video["codec_name"]]

    stop = end_seconds if end_seconds is not None else probe_duration_or_none(input)
    reporter = ProgressReporter()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            head, tail, audio = work / "head.ts", work / "tail.ts", work / "audio.mka"

            reporter.update(0.1, f"re-encoding {keyframe - start_seconds:.2f}s up to the next keyframe", force=True)
            head_args = ["-ss", format_time(start_seconds), "-i", str(input)]
            head_args += ["-t", format_time(keyframe - start_seconds), "-map", "0:v:0", "-an"]
            head_args += ["-c:v", encoder, "-crf", _REENCODE_CRF, "-fps_mode", "passthrough"]
            if video.get("pix_fmt"):
                head_args += ["-pix_fmt", video["pix_fmt"]]
            run_ffmpeg([*head_args, str(head)])

            reporter.update(0.5, "copying the rest", force=True)
            tail_args = ["-ss", format_time(keyframe), "-i", str(input)]
            if end_seconds is not None:
                tail_args += ["-t", format_time(end_seconds - keyframe)]
            run_ffmpeg([*tail_args, "-map", "0:v:0", "-an", "-c:v", "copy", "-bsf:v", bsf, str(tail)])

            if has_audio:
                # Output-side seek: an input-side one on a copy starts at the
                # video keyframe and carries seconds of audio from before the cut.
                audio_args = ["-i", str(input), "-ss", format_time(start_seconds)]
                if end_seconds is not None:
                    audio_args += ["-t", format_time(end_seconds - start_seconds)]
                run_ffmpeg([*audio_args, "-map", "0:a", "-vn", "-c:a", "copy", str(audio)])

            concat_list = work / "concat.txt"
            concat_list.write_text(f"file '{head.as_posix()}'\nfile '{tail.as_posix()}'\n", encoding="utf-8")
            mux = ["-f", "concat", "-safe", "0", "-i", str(concat_list)]
            if has_audio:
                mux += ["-i", str(audio), "-map", "0:v", "-map", "1:a"]
            run_ffmpeg([*mux, "-c", "copy", "-avoid_negative_ts", "make_zero", str(output)])

        reporter.update(0.9, "checking the result", force=True)
        problem = _verify_cut(output, None if stop is None else stop - start_seconds)
    except (subprocess.CalledProcessError, OSError) as e:
        problem = f"ffmpeg failed ({e})"
    if problem:
        output.unlink(missing_ok=True)
        return problem
    reporter.finish()
    print(
        f"Smart cut: re-encoded {keyframe - start_seconds:.2f}s up to the keyframe at {keyframe:.2f}s, copied the rest."
    )
    return None


def _verify_cut(output: Path, expected: float | None) -> str | None:
    """Decode a smart cut once and check its length.

    Args:
        output: The spliced file.
        expected: Length the cut should have, in seconds, or None if unknown.

    Returns:
        None when the file decodes cleanly at the expected length, else why not.
    """
    errors = run_ffmpeg_stderr(["-v", "error", "-i", str(output), "-f", "null", "-"]).strip()
    if errors:
        return "the spliced file did not decode cleanly"
    if expected is not None:
        actual = probe_duration_or_none(output)
        if actual is None or abs(actual - expected) > _SMART_CUT_DURATION_SLACK:
            return "the spliced file came out the wrong length"
    return None


def trim(
    input: Path,
    output: Path,
    start: str,
    end: str | None = None,
    mode: str = MODE_AUTO,
) -> str:
    """Trim a media file by time range.

    A stream copy cannot begin mid-GOP, so ``-ss`` seeks backwards to the
    nearest keyframe. On a sparsely-keyed source — a long GOP, a low frame
    rate, a screen recording — that can be seconds away from the requested cut,
    and trimming the first few seconds off such a file used to report success
    while handing back something indistinguishable from the original. The
    default now checks where a copy would actually land and re-encodes when
    that is not where the user asked for.

    Args:
        input: Source media file.
        output: Destination file path.
        start: Start time (HH:MM:SS, MM:SS, or seconds). Output begins here.
        end: Optional end time in the same formats; when omitted, the output
            runs to the source's end.
        mode: ``"auto"`` (default) stream-copies when a keyframe lands on the
            start, and otherwise smart-cuts (re-encoding only up to the next
            keyframe), falling back to a full re-encode when that is not
            possible; ``"fast"`` always stream-copies, accepting the keyframe
            snap; ``"precise"`` always re-encodes.

    Returns:
        ``"copy"``, ``"smart"`` or ``"reencode"``: the strategy actually used.

    Raises:
        ValueError: If *mode* is unrecognised or a timestamp cannot be parsed.
        subprocess.CalledProcessError: If ffmpeg fails.
    """
    start_seconds = parse_time(start)
    reencode, keyframe = _should_reencode(input, start_seconds, mode)

    if reencode and mode == MODE_AUTO and has_video_stream(input):
        end_seconds = None if end is None else parse_time(end)
        why_not = _smart_cut(input, output, start_seconds, end_seconds)
        if why_not is None:
            return STRATEGY_SMART
        print(f"Smart cut not possible: {why_not}. Re-encoding the whole range instead.")

    args = ["-ss", start, "-i", str(input)]
    if end is not None:
        duration = parse_time(end) - parse_time(start)
        args += ["-t", format_time(duration)]
    else:
        source_duration = probe_duration_or_none(input)
        duration = None if source_duration is None else max(0.0, source_duration - start_seconds)

    if reencode:
        # Input seeking stays: modern ffmpeg seeks to the preceding keyframe and
        # then decodes and discards up to the exact point, so the cut is frame
        # accurate without the cost of decoding the whole file. The audio is
        # copied — it has no GOP to be inaccurate about, and the container is
        # the source's own, so its codec is muxable by definition. No video
        # encoder is named for the same reason: ffmpeg's default for this
        # container is muxable into it, which libx264 is not for every one.
        args += ["-c:a", "copy"]
        if has_video_stream(input):
            args += ["-crf", _REENCODE_CRF]
    else:
        args += ["-c", "copy", "-avoid_negative_ts", "make_zero"]
    args.append(str(output))

    if reencode and mode == MODE_AUTO:
        landed = "an unknown position" if keyframe is None else f"{keyframe:.2f}s"
        print(f"Re-encoding: a stream copy would have started at {landed}, not {start_seconds:.2f}s.")

    # ffmpeg reports its position within the output, which for a trim is the
    # length of the kept range rather than of the source.
    run_ffmpeg_with_progress(args, total_seconds=duration)
    return STRATEGY_REENCODE if reencode else STRATEGY_COPY


_EXAMPLES = """
examples:
  uv run main.py av.trim input.mp4 00:03                       # skip the first three seconds
  uv run main.py av.trim input.mp4 1:03 5:04                   # keep 1m03s..5m04s
  uv run main.py av.trim input.mp4 1:03 5:04 --output cut.mp4  # custom output filename
  uv run main.py av.trim input.mp4 00:03 --mode fast           # snap to a keyframe, never re-encode
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py av.trim",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Source media file (bare name resolves to inputs/)",
    )
    parser.add_argument(
        "start",
        metavar="START",
        help="Start time (HH:MM:SS, MM:SS, or seconds)",
    )
    parser.add_argument(
        "end",
        nargs="?",
        default=None,
        metavar="END",
        help="Optional end time; defaults to end-of-file",
    )
    parser.add_argument(
        "--mode",
        choices=TRIM_MODES,
        default=MODE_AUTO,
        help=(
            "auto (default): stream-copy when a keyframe lands on the start, otherwise "
            "re-encode only up to the next keyframe and copy the rest (H.264/HEVC), "
            "or the whole range for other codecs; fast: always stream-copy, snapping "
            "to the nearest keyframe; precise: always re-encode"
        ),
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        metavar="PATH",
        help="Output file or directory (default: timestamp-named in outputs/av/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to trim()."""
    args = get_parser().parse_args()

    input_file = args.input
    input_file = resolve_input(input_file, "av")

    output = resolve_output(args.output, theme="av", ext=input_file.suffix)

    try:
        trim(input_file, output, start=args.start, end=args.end, mode=args.mode)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    move_to_past_inputs("av", input_file)
    print(output)
    sys.exit(0)
