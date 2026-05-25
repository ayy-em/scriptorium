"""Document format conversion: docx, rtf, md, html, pdf, txt via pandoc (+ pypdf for PDF extraction)."""

import argparse
from collections.abc import Callable
from pathlib import Path
import shutil
import subprocess
import sys

from core.argparse import ScriptoriumParser
from scripts.formats._utils import (
    BatchConvertError,
    formats_inputs_dir,
    formats_outputs_dir,
    run_convert,
)

TITLE = "Convert documents"
DESCRIPTION = "Convert documents between docx, rtf, md, html, pdf, and txt formats."

DOCS_EXTS = frozenset({".docx", ".rtf", ".md", ".html", ".htm", ".pdf", ".txt"})
_OUT_FORMATS = ("pdf", "md", "txt", "rtf", "docx", "html")

_PANDOC_INSTALL_HINT = (
    "pandoc is required but was not found on PATH. "
    "Install it: macOS `brew install pandoc`, Debian/Ubuntu `apt install pandoc`, "
    "Windows `winget install JohnMacFarlane.Pandoc`."
)


class PandocMissingError(RuntimeError):
    """Raised when pandoc is needed but not available on PATH."""


def _has_pandoc() -> bool:
    return shutil.which("pandoc") is not None


def _has_weasyprint() -> bool:
    return shutil.which("weasyprint") is not None


def _pandoc_convert(source: Path, output: Path) -> None:
    if not _has_pandoc():
        raise PandocMissingError(_PANDOC_INSTALL_HINT)
    args = ["pandoc", str(source), "-o", str(output), "--standalone"]
    if output.suffix.lower() == ".pdf" and _has_weasyprint():
        args.extend(["--pdf-engine=weasyprint"])
    subprocess.run(args, check=True, capture_output=True, text=True)


def _copy(source: Path, output: Path) -> None:
    output.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def _extract_pdf_text(source: Path, output: Path) -> None:
    from pypdf import PdfReader  # noqa: PLC0415

    reader = PdfReader(str(source))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    output.write_text(text, encoding="utf-8")


_SUPPORTED_INPUT_EXTS = {ext.lstrip(".") for ext in DOCS_EXTS}


def _dispatcher(source_ext: str, target_ext: str) -> Callable[[Path, Path], None]:
    src = source_ext.lstrip(".").lower()
    dst = target_ext.lstrip(".").lower()
    if src == "doc":
        raise ValueError("binary .doc files are not supported. Convert to .docx first using LibreOffice or Word.")
    if src not in _SUPPORTED_INPUT_EXTS:
        raise ValueError(f"unsupported source extension: .{src}")
    if {src, dst} == {"txt", "md"} or src == dst:
        return _copy
    if src == "pdf" and dst == "txt":
        return _extract_pdf_text
    return _pandoc_convert


def convert(source: Path, to_format: str, outputs_dir: Path) -> list[Path]:
    """Convert a single document or every document in a directory to ``to_format``.

    Args:
        source: Single file or directory of documents.
        to_format: Target extension without dot (e.g. "pdf", "md").
        outputs_dir: Output directory.

    Returns:
        List of successfully created output paths.

    Raises:
        ValueError: For unsupported source/target combinations.
        PandocMissingError: If pandoc is required but not on PATH.
        BatchConvertError: If batch mode has any failures.
    """
    target = to_format.lstrip(".").lower()
    if target not in _OUT_FORMATS:
        raise ValueError(f"unsupported target format {to_format!r}. Choose one of: {', '.join(_OUT_FORMATS)}")

    def _fn(inp: Path, out: Path) -> None:
        _dispatcher(inp.suffix, out.suffix)(inp, out)

    return run_convert(source, DOCS_EXTS, outputs_dir, target, _fn)


_EXAMPLES = """
examples:
  uv run main.py formats.convert_docs report.docx --to pdf
  uv run main.py formats.convert_docs notes.md --to docx
  uv run main.py formats.convert_docs --to md                     # batch every file in formats/inputs/
  uv run main.py formats.convert_docs paper.pdf --to txt          # text extraction via pypdf
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = ScriptoriumParser(
        description=DESCRIPTION,
        prog="uv run main.py formats.convert_docs",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        type=Path,
        nargs="?",
        help="Source file or directory (default: formats/inputs/)",
    )
    parser.add_argument(
        "--to",
        required=True,
        dest="to_format",
        metavar="FORMAT",
        choices=_OUT_FORMATS,
        help="Target format",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        metavar="DIR",
        help="Output directory (default: formats/outputs/)",
    )
    return parser


def run() -> None:
    """CLI entrypoint. Parse arguments and dispatch to convert()."""
    args = get_parser().parse_args()
    source = args.source or formats_inputs_dir()
    out_dir = args.outputs or formats_outputs_dir()

    try:
        outputs = convert(source, args.to_format, out_dir)
        for o in outputs:
            print(o)
        sys.exit(0)
    except PandocMissingError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    except BatchConvertError as e:
        for o in e.succeeded:
            print(o)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
