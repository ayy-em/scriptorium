"""CLI and programmatic interface for converting tabular data files between formats."""

import argparse
from pathlib import Path
import sys

import pandas as pd

from scripts.formats._utils import (
    TABULAR_EXTS,
    BatchConvertError,
    formats_inputs_dir,
    formats_outputs_dir,
    run_convert,
)

TITLE = "Convert tabular"
DESCRIPTION = "Convert spreadsheet and data files between CSV, XLSX, ODS, JSON, and TSV."

_TABULAR_OUT_FORMATS = ["csv", "xlsx", "ods", "json", "tsv"]


def _convert(input_path: Path, output: Path, sheet: str | None) -> None:
    """Read a tabular file and write it in the target format.

    Args:
        input_path: Source tabular file.
        output: Destination file.
        sheet: Sheet name or index for multi-sheet Excel/ODS inputs. None = first sheet.
    """
    in_ext = input_path.suffix.lower()
    out_ext = output.suffix.lower()

    if in_ext == ".csv":
        df = pd.read_csv(input_path)
    elif in_ext == ".tsv":
        df = pd.read_csv(input_path, sep="\t")
    elif in_ext in {".xlsx", ".ods"}:
        kwargs: dict = {"sheet_name": sheet} if sheet else {}
        df = pd.read_excel(input_path, **kwargs)
    elif in_ext == ".json":
        df = pd.read_json(input_path)
    else:
        raise ValueError(f"Unsupported input format: {in_ext}")

    if out_ext == ".csv":
        df.to_csv(output, index=False)
    elif out_ext == ".tsv":
        df.to_csv(output, sep="\t", index=False)
    elif out_ext == ".xlsx":
        df.to_excel(output, index=False)
    elif out_ext == ".ods":
        df.to_excel(output, engine="odf", index=False)
    elif out_ext == ".json":
        df.to_json(output, orient="records", indent=2)
    else:
        raise ValueError(f"Unsupported output format: {out_ext}")


def convert(
    source: Path,
    to_format: str,
    outputs_dir: Path,
    *,
    sheet: str | None = None,
) -> list[Path]:
    """Convert a single tabular file or a directory of tabular files to a target format.

    Args:
        source: Source file or directory of tabular files.
        to_format: Target format extension without leading dot (e.g. "csv", "xlsx").
        outputs_dir: Directory where converted files are written.
        sheet: Sheet name or index for multi-sheet Excel/ODS inputs.

    Returns:
        List of successfully created output Paths.

    Raises:
        ValueError: If the input format is unsupported.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """

    def _fn(inp: Path, out: Path) -> None:
        _convert(inp, out, sheet)

    return run_convert(source, TABULAR_EXTS, outputs_dir, to_format, _fn)


_EXAMPLES = """
examples:
  uv run main.py formats.convert_tabular data.csv --to xlsx
  uv run main.py formats.convert_tabular --to csv
  uv run main.py formats.convert_tabular report.xlsx --to json --sheet Summary
"""


def get_parser() -> argparse.ArgumentParser:
    """Return the argument parser for this script."""
    parser = argparse.ArgumentParser(
        description=DESCRIPTION,
        prog="uv run main.py formats.convert_tabular",
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
        choices=_TABULAR_OUT_FORMATS,
        help="Target format",
    )
    parser.add_argument(
        "--sheet",
        default=None,
        metavar="NAME",
        help="Sheet name or index for multi-sheet Excel/ODS input (default: first sheet).",
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
        outputs = convert(source, args.to_format, out_dir, sheet=args.sheet)
        for o in outputs:
            print(o)
        sys.exit(0)
    except BatchConvertError as e:
        for o in e.succeeded:
            print(o)
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
