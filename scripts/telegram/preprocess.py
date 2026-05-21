"""Compress a Telegram export ``result.json`` into per-year JSONs for downstream embedding."""

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

import ijson

from core.paths import inputs_dir, outputs_dir

TITLE = "Preprocess Telegram export for embeddings"
DESCRIPTION = "Strip the fat, rename keys, split by year, and emit a single zip ready for embedding."

SCHEMA_VERSION = 1

# Map short → original key. Embedded in the manifest so consumers don't hard-code abbreviations.
_FIELD_MAP: dict[str, str] = {
    "t": "type",
    "d": "date",
    "f": "from",
    "e": "text_entities",
    "r": "reply_to_message_id",
    "fwd": "forwarded_from",
    "m": "media_type",
}


def _inputs() -> Path:
    return inputs_dir("telegram")


def _outputs() -> Path:
    return outputs_dir("telegram")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _trim_message(msg: dict, *, keep_service: bool) -> dict | None:
    """Apply the trim/rename rules; return None for messages that should be dropped."""
    msg_type = msg.get("type")
    if msg_type != "message" and not keep_service:
        return None

    out: dict = {
        "t": msg_type,
        "d": msg.get("date"),
        "f": msg.get("from"),
        "e": msg.get("text_entities", []),
    }
    if (reply := msg.get("reply_to_message_id")) is not None:
        out["r"] = reply
    if (fwd := msg.get("forwarded_from")) is not None:
        out["fwd"] = fwd
    if (media := msg.get("media_type")) is not None:
        out["m"] = media
    return out


_YEAR_PREFIX_LEN = 4


def _year_of(message: dict) -> int | None:
    date = message.get("d")
    if not isinstance(date, str) or len(date) < _YEAR_PREFIX_LEN:
        return None
    try:
        return int(date[:_YEAR_PREFIX_LEN])
    except ValueError:
        return None


def preprocess(source: Path, output_zip: Path, *, keep_service: bool = False) -> Path:
    """Read ``source`` (a Telegram export ``result.json``) and write ``output_zip``.

    The zip contains ``messages_YYYY.json`` for each calendar year covered, plus
    ``manifest.json`` with the source hash, message counts, schema version, and
    short-key field map.

    Args:
        source: Path to the raw export JSON.
        output_zip: Destination .zip path.
        keep_service: When True, retain service messages (``type != "message"``).
            Default is to drop them.

    Returns:
        ``output_zip`` on success.

    Raises:
        FileNotFoundError: If ``source`` does not exist.
    """
    if not source.is_file():
        raise FileNotFoundError(f"export file not found: {source}")

    by_year: dict[int, list[dict]] = {}
    skipped_no_date = 0

    with open(source, "rb") as f:
        for raw in ijson.items(f, "messages.item"):
            trimmed = _trim_message(raw, keep_service=keep_service)
            if trimmed is None:
                continue
            year = _year_of(trimmed)
            if year is None:
                skipped_no_date += 1
                continue
            by_year.setdefault(year, []).append(trimmed)

    total_messages = sum(len(v) for v in by_year.values())
    per_year_counts = {str(year): len(by_year[year]) for year in sorted(by_year)}

    manifest = {
        "source_name": source.name,
        "source_sha256": _sha256(source),
        "schema_version": SCHEMA_VERSION,
        "total_messages": total_messages,
        "per_year_counts": per_year_counts,
        "field_map": _FIELD_MAP,
        "keep_service": keep_service,
        "skipped_no_date": skipped_no_date,
    }

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for year in sorted(by_year):
            payload = json.dumps(by_year[year], ensure_ascii=False).encode("utf-8")
            zf.writestr(f"messages_{year}.json", payload)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    return output_zip


_EXAMPLES = """
examples:
  uv run main.py telegram.preprocess result.json
  uv run main.py telegram.preprocess result.json --output processed
  uv run main.py telegram.preprocess result.json --keep-service
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py telegram.preprocess",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Path to Telegram export result.json (bare name resolves to telegram/inputs/)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="processed",
        metavar="NAME",
        help="Output zip filename stem (default: processed → processed.zip)",
    )
    parser.add_argument(
        "--keep-service",
        action="store_true",
        help="Retain service messages (joins, pins, etc.); default drops them",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to preprocess()."""
    args = get_parser().parse_args()

    source = args.source
    if source.parent == Path("."):
        source = _inputs() / source.name

    stem = args.output if args.output.endswith(".zip") else f"{args.output}.zip"
    output = _outputs() / stem

    try:
        result = preprocess(source, output, keep_service=args.keep_service)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"wrote {result}")
    sys.exit(0)
