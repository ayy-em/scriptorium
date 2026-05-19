"""Transcribe an audio file to text using a configured speech-to-text provider."""

import argparse
from pathlib import Path
import sys

from core.argparse import ScriptoriumParser
from core.paths import inputs_dir, outputs_dir
from scripts.speech._providers import (
    DEFAULT_PROVIDER,
    SUPPORTED_PROVIDERS,
    MissingCredentialsError,
    TranscriptionProvider,
    get_provider,
)

TITLE = "Transcribe audio to text"
DESCRIPTION = "Send an audio file to a speech-to-text provider and write the transcript to outputs/."

_FORMATS = ("txt", "md", "rtf")
_DEFAULT_FORMAT = "txt"


def _inputs() -> Path:
    return inputs_dir("speech")


def _outputs() -> Path:
    return outputs_dir("speech")


def _render(text: str, fmt: str, source_name: str) -> str:
    if fmt == "txt":
        return text
    if fmt == "md":
        return f"# Transcript: {source_name}\n\n{text}\n"
    if fmt == "rtf":
        escaped = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        body = escaped.replace("\n", "\\par\n")
        return "{\\rtf1\\ansi\\deff0\n" + body + "\n}"
    raise ValueError(f"unsupported format: {fmt}")


def transcribe(
    audio_path: Path,
    output_path: Path,
    *,
    provider: TranscriptionProvider,
    fmt: str = _DEFAULT_FORMAT,
) -> Path:
    """Transcribe ``audio_path`` and write the result to ``output_path`` in the chosen format.

    Returns the output path on success. Raises FileNotFoundError if the audio is missing,
    ValueError for an unknown format, and MissingCredentialsError if the provider's
    API key is not configured.
    """
    if not audio_path.is_file():
        raise FileNotFoundError(f"audio file not found: {audio_path}")
    if fmt not in _FORMATS:
        raise ValueError(f"unsupported format {fmt!r}. choose one of: {', '.join(_FORMATS)}")

    text = provider.transcribe(audio_path)
    rendered = _render(text, fmt, audio_path.name)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")
    return output_path


_EXAMPLES = """
examples:
  uv run main.py speech.transcribe meeting.m4a
  uv run main.py speech.transcribe meeting.m4a --output transcript --format md
  uv run main.py speech.transcribe interview.mp3 --tts-provider openai --format rtf
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py speech.transcribe",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "audio",
        type=Path,
        help="audio file to transcribe (bare name resolves to speech/inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        metavar="NAME",
        help="output filename stem (default: audio stem)",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=_FORMATS,
        default=_DEFAULT_FORMAT,
        help=f"output format (default: {_DEFAULT_FORMAT})",
    )
    parser.add_argument(
        "--tts-provider",
        choices=SUPPORTED_PROVIDERS,
        default=DEFAULT_PROVIDER,
        ui_label="Provider",
        help=f"speech-to-text provider (default: {DEFAULT_PROVIDER})",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to transcribe()."""
    args = get_parser().parse_args()

    audio = args.audio
    if audio.parent == Path("."):
        audio = _inputs() / audio.name

    stem = args.output or audio.stem
    output_path = _outputs() / f"{stem}.{args.format}"

    try:
        provider = get_provider(args.tts_provider)
        result = transcribe(audio, output_path, provider=provider, fmt=args.format)
    except MissingCredentialsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"wrote transcript to {result}")
    sys.exit(0)
