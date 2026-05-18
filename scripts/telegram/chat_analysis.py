"""Generate a descriptive-analytics report from a Telegram personal-chat export."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import zipfile

from core.argparse import ScriptoriumParser
from core.paths import inputs_dir as _core_inputs_dir
from core.paths import outputs_dir as _core_outputs_dir
from scripts.telegram._parsing import InvalidExportError, load_chat

TITLE = "Analyze your Telegram chat history and generate a report full of insights"
DESCRIPTION = (
    "Generate a descriptive-analytics report (flashy PDF, stats and charts) based on a Telegram chat history export."
)

_CHARTS_DIR = "charts"
_JSON_NAME = "chat_analytics.json"
_PDF_NAME = "chat_analytics.pdf"

_EXAMPLES = """
examples:
  uv run main.py telegram.chat_analysis result.json
  uv run main.py telegram.chat_analysis /path/to/result.json --outputs /tmp/reports
"""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_").lower()[:40]
    return slug or "chat"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def chat_analysis(source: Path, outputs_dir: Path) -> Path:
    """Produce the chat_analysis ``.zip`` for ``source`` under ``outputs_dir``.

    Returns the path to the produced archive. Raises ``InvalidExportError`` or
    ``FileNotFoundError`` on bad input.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Defer heavy plotting/PDF imports until we know we'll need them.
    from scripts.telegram import _charts, _metrics, _pdf  # noqa: PLC0415

    metadata, messages = load_chat(source)
    source_sha = _sha256(source)
    analytics = _metrics.build_analytics(
        metadata,
        messages,
        source_file_name=source.name,
        source_sha256=source_sha,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir)
        charts_dir = staging / _CHARTS_DIR
        charts_dir.mkdir()

        chart_paths = {
            "monthly_volume": _charts.render_monthly_volume(analytics, charts_dir),
            "activity_heatmap": _charts.render_activity_heatmap(analytics, charts_dir),
            "message_share": _charts.render_message_share(analytics, charts_dir),
            "reply_latency": _charts.render_reply_latency(analytics, charts_dir),
            "emoji_cloud": _charts.render_emoji_cloud(analytics, charts_dir),
        }
        per_user = _metrics.per_user_word_counts(messages, [p.id for p in metadata.participants])
        word_counts, word_shares = _metrics.shared_word_counts(per_user)
        chart_paths["word_cloud"] = _charts.render_word_cloud(word_counts, word_shares, charts_dir)

        json_path = staging / _JSON_NAME
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(analytics, fh, ensure_ascii=False, indent=2)

        pdf_path = staging / _PDF_NAME
        _pdf.render_pdf(analytics, chart_paths, pdf_path)

        slug = _slugify(metadata.name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = outputs_dir / f"chat_analysis_{slug}_{stamp}.zip"
        _build_zip(staging, zip_path)

    return zip_path


def _build_zip(staging: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(staging))


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for telegram.chat_analysis."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py telegram.chat_analysis",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        ui_label="Chat export JSON",
        help="Path to the Telegram personal-chat export result.json (bare filename resolves from telegram/inputs/).",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory for the report .zip (default: telegram/outputs/).",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parses argv and dispatches to chat_analysis()."""
    args = get_parser().parse_args()
    source: Path = args.source
    if source.parent == Path("."):
        source = _core_inputs_dir("telegram") / source.name
    out_dir: Path = args.outputs or _core_outputs_dir("telegram")
    try:
        out_path = chat_analysis(source, out_dir)
    except (FileNotFoundError, InvalidExportError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001 — surface unexpected errors to the CLI
        print(f"unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
    print(out_path)
