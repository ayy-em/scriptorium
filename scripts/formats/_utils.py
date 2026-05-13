"""Shared utilities for the formats script bundle."""

from collections.abc import Callable
from pathlib import Path

from core.paths import inputs_dir, outputs_dir

VIDEO_EXTS = frozenset({".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv"})
AUDIO_EXTS = frozenset({".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus"})
IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"})
TABULAR_EXTS = frozenset({".csv", ".tsv", ".xlsx", ".ods", ".json"})

QUALITY_PRESETS: dict[str, dict[str, str]] = {
    "low": {"crf": "28", "audio_bitrate": "96k"},
    "medium": {"crf": "23", "audio_bitrate": "128k"},
    "high": {"crf": "18", "audio_bitrate": "192k"},
    "max": {"crf": "0", "audio_bitrate": "320k"},
}


class BatchConvertError(RuntimeError):
    """Raised when one or more files fail in a batch run.

    Carries the list of successfully created outputs so callers can inspect partial results.
    """

    def __init__(self, message: str, succeeded: list[Path]) -> None:
        """Initialize with failure summary and list of paths that did succeed."""
        super().__init__(message)
        self.succeeded = succeeded


def formats_inputs_dir() -> Path:
    """Return the default formats inputs directory, creating it if needed."""
    return inputs_dir("formats")


def formats_outputs_dir() -> Path:
    """Return the default formats outputs directory, creating it if needed."""
    return outputs_dir("formats")


def find_files(directory: Path, exts: frozenset[str]) -> list[Path]:
    """Return a sorted list of files with matching extensions in a directory (non-recursive).

    Args:
        directory: Directory to scan.
        exts: Set of lowercase extensions (with dot) to match.

    Returns:
        Sorted list of matching Paths.
    """
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in exts)


def run_convert(
    source: Path,
    exts: frozenset[str],
    outputs_dir_path: Path,
    ext_out: str,
    fn: Callable[[Path, Path], None],
) -> list[Path]:
    """Convert a single file or all matching files in a directory.

    Single-file mode raises on error. Batch mode continues on per-file errors and raises
    BatchConvertError at the end, which carries the list of files that did succeed.

    Args:
        source: Source file or directory.
        exts: Extensions to match when source is a directory.
        outputs_dir_path: Directory where outputs are written.
        ext_out: Target extension without leading dot (e.g. "mp4").
        fn: Callable that accepts (input_path, output_path) and performs the conversion.

    Returns:
        List of successfully created output Paths.

    Raises:
        subprocess.CalledProcessError: If conversion fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """
    outputs_dir_path.mkdir(parents=True, exist_ok=True)
    out_suffix = f".{ext_out.lstrip('.')}"

    if source.is_file():
        output = outputs_dir_path / f"{source.stem}{out_suffix}"
        fn(source, output)
        return [output]

    files = find_files(source, exts)
    successes: list[Path] = []
    failures: list[str] = []

    for f in files:
        output = outputs_dir_path / f"{f.stem}{out_suffix}"
        try:
            fn(f, output)
            successes.append(output)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise BatchConvertError(
            f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}",
            successes,
        )

    return successes
