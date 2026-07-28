"""Shared utilities for the formats script bundle."""

from collections.abc import Callable
from pathlib import Path

from core.outputs import deduplicate, default_stem
from core.paths import inputs_dir, move_to_past_inputs

_ARCHIVE_THEME = "formats"

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


def find_files(directory: Path, exts: frozenset[str]) -> list[Path]:
    """Return a sorted list of files with matching extensions in a directory (non-recursive).

    Args:
        directory: Directory to scan.
        exts: Set of lowercase extensions (with dot) to match.

    Returns:
        Sorted list of matching Paths.
    """
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in exts)


def single_source(source: Path, exts: frozenset[str]) -> Path | None:
    """Return the lone matching file when *source* effectively refers to one file.

    The web UI uploads even a single file into a per-batch directory, so a
    directory here does not mean "many files". Callers use this so that a
    one-file job behaves like one file — notably so an explicit ``--output``
    filename is not discarded by the batch path.

    Args:
        source: Source file or directory.
        exts: Extensions to match when *source* is a directory.

    Returns:
        The single file, or None when *source* holds zero or several matches.
    """
    if source.is_file():
        return source
    if not source.is_dir():
        return None
    files = find_files(source, exts)
    return files[0] if len(files) == 1 else None


def run_convert(
    source: Path,
    exts: frozenset[str],
    outputs_dir_path: Path,
    ext_out: str,
    fn: Callable[[Path, Path], None],
    explicit_output: Path | None = None,
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
        explicit_output: Exact output path the user asked for. Honoured only when
            the job resolves to a single file; ignored for a real batch, where
            one filename cannot name several outputs.

    Returns:
        List of successfully created output Paths.

    Raises:
        subprocess.CalledProcessError: If conversion fails in single-file mode.
        BatchConvertError: If any files fail in batch mode (after processing all).
    """
    outputs_dir_path.mkdir(parents=True, exist_ok=True)
    out_suffix = f".{ext_out.lstrip('.')}"
    stem = default_stem()

    lone = single_source(source, exts)
    if lone is not None:
        output = explicit_output or deduplicate(outputs_dir_path / f"{stem}{out_suffix}")
        output.parent.mkdir(parents=True, exist_ok=True)
        fn(lone, output)
        move_to_past_inputs(_ARCHIVE_THEME, lone)
        return [output]

    files = find_files(source, exts)
    successes: list[Path] = []
    failures: list[str] = []

    for i, f in enumerate(files, 1):
        output = deduplicate(outputs_dir_path / f"{stem}_{i:03d}{out_suffix}")
        try:
            fn(f, output)
            successes.append(output)
            move_to_past_inputs(_ARCHIVE_THEME, f)
        except Exception as e:
            failures.append(f"{f.name}: {e}")

    if failures:
        bullet_list = "\n".join(f"  - {msg}" for msg in failures)
        raise BatchConvertError(
            f"{len(failures)} of {len(files)} file(s) failed:\n{bullet_list}",
            successes,
        )

    return successes
