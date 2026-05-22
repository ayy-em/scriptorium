"""Generate a descriptive-analytics report from a Telegram group-chat export."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from core.argparse import ScriptoriumParser
from core.paths import inputs_dir as _core_inputs_dir
from core.paths import outputs_dir as _core_outputs_dir
from scripts.telegram._group_metrics import DEFAULT_MSG_SHARE_THRESHOLD
from scripts.telegram._group_parsing import InvalidExportError

TITLE = "Analyze a Telegram group chat and generate a visual analytics report"
DESCRIPTION = (
    "Generate a multi-page PDF report with charts and analytics from a "
    "Telegram group/supergroup chat history export (JSON)."
)

_CHARTS_DIR = "charts"
_JSON_NAME = "group_analytics.json"
_PDF_NAME = "group_analytics.pdf"

_DEFAULT_SOURCE = "result.json"

_EXAMPLES = """
examples:
  uv run main.py telegram.group_analysis
  uv run main.py telegram.group_analysis /path/to/result.json
  uv run main.py telegram.group_analysis --msg-share-threshold 2
  uv run main.py telegram.group_analysis --outputs /tmp/reports
"""


def _slugify(name: str) -> str:
    slug = re.sub(r"[^\w]+", "_", name, flags=re.UNICODE).strip("_").lower()[:40]
    return slug or "group"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def group_analysis(
    source: Path,
    outputs_dir: Path,
    msg_share_threshold: int = DEFAULT_MSG_SHARE_THRESHOLD,
    count_bots: bool = False,
) -> Path:
    """Produce the group_analysis ``.zip`` for ``source`` under ``outputs_dir``.

    Args:
        source: Path to the Telegram group chat export result.json.
        outputs_dir: Directory to write the output .zip into.
        msg_share_threshold: Minimum % of total messages to include a user.
        count_bots: If True, include detected bot accounts in the analysis.

    Returns:
        Path to the produced archive.
    """
    if not source.exists():
        raise FileNotFoundError(f"Source file not found: {source}")

    outputs_dir.mkdir(parents=True, exist_ok=True)

    from scripts.telegram import _group_charts, _group_metrics, _group_pdf  # noqa: PLC0415
    from scripts.telegram._group_parsing import load_group_chat  # noqa: PLC0415

    metadata, messages, sender_lookup, bot_ids = load_group_chat(source)
    source_sha = _sha256(source)
    analytics = _group_metrics.build_group_analytics(
        metadata,
        messages,
        sender_lookup,
        msg_share_threshold=msg_share_threshold,
        count_bots=count_bots,
        bot_ids=bot_ids,
        source_file_name=source.name,
        source_sha256=source_sha,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        staging = Path(tmpdir)
        charts_dir = staging / _CHARTS_DIR
        charts_dir.mkdir()

        chart_paths = {
            "monthly_volume": _group_charts.render_monthly_volume(analytics, charts_dir),
            "user_share_top10": _group_charts.render_user_share_top10(analytics, charts_dir),
            "activity_heatmap": _group_charts.render_activity_heatmap(analytics, charts_dir),
            "reply_network": _group_charts.render_reply_network(analytics, charts_dir),
            "profanity_podium": _group_charts.render_profanity_podium(analytics, charts_dir),
            "sentiment_flow": _group_charts.render_sentiment_flow(analytics, charts_dir),
            "yearly_volume": _group_charts.render_yearly_volume(analytics, charts_dir),
        }
        active_ids = [p["id"] for p in analytics["participants"]]
        word_counts, per_user_counts = _group_metrics.group_word_counts(messages, active_ids)
        chart_paths["word_cloud"] = _group_charts.render_word_cloud(
            word_counts,
            per_user_counts,
            analytics,
            charts_dir,
        )

        json_path = staging / _JSON_NAME
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(analytics, fh, ensure_ascii=False, indent=2)

        pdf_path = staging / _PDF_NAME
        _group_pdf.render_group_pdf(analytics, chart_paths, pdf_path)

        slug = _slugify(metadata.name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = outputs_dir / f"group_analysis_{slug}_{stamp}.zip"
        _build_zip(staging, zip_path)

    _archive_source(source)
    return zip_path


def _archive_source(source: Path) -> Path | None:
    """Move a processed source file to ``inputs/telegram/processed/``."""
    inputs_root = _core_inputs_dir("telegram").resolve()
    try:
        source.resolve().relative_to(inputs_root)
    except ValueError:
        return None
    dest_dir = inputs_root / "telegram" / "processed"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%d%m%y_%H%M%S")
    dest = dest_dir / f"result_{stamp}{source.suffix}"
    shutil.move(str(source), str(dest))
    return dest


def _build_zip(staging: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=path.relative_to(staging))


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for telegram.group_analysis."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py telegram.group_analysis",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        default=None,
        ui_label="Group chat export JSON",
        help=f"Path to the Telegram group-chat export result.json (default: inputs/{_DEFAULT_SOURCE}).",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory for the report .zip (default: outputs/telegram/).",
    )
    parser.add_argument(
        "--msg-share-threshold",
        type=int,
        default=DEFAULT_MSG_SHARE_THRESHOLD,
        metavar="PCT",
        help=(
            "Minimum share (in %%) of total messages a user must have sent to appear "
            f"in the report (default: {DEFAULT_MSG_SHARE_THRESHOLD})."
        ),
    )
    parser.add_argument(
        "--count-bots",
        action="store_true",
        default=False,
        help="Include bot accounts in the analysis (excluded by default).",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parses argv and dispatches to group_analysis()."""
    args = get_parser().parse_args()
    source: Path = args.source
    if source is None:
        source = _core_inputs_dir("telegram") / _DEFAULT_SOURCE
    elif source.parent == Path("."):
        source = _core_inputs_dir("telegram") / source.name
    out_dir: Path = args.outputs or _core_outputs_dir("telegram")
    try:
        out_path = group_analysis(
            source,
            out_dir,
            msg_share_threshold=args.msg_share_threshold,
            count_bots=args.count_bots,
        )
    except (FileNotFoundError, InvalidExportError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"unexpected error: {e}", file=sys.stderr)
        sys.exit(1)
    print(out_path)
