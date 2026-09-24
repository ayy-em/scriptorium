"""Report third-party downloads through the same progress channel as everything else.

rembg fetches model weights with ``pooch.retrieve(..., progressbar=True)``,
which draws a tqdm bar on stderr. In the web UI that bar is invisible until
the run ends, so a first run of a new model looks hung for the length of a
200MB download. pooch accepts any object with ``total``, ``update``,
``reset`` and ``close`` in place of ``True``; this module supplies one that
forwards to ``core.progress.ProgressReporter``, and a context manager that
swaps it in for the duration of a call that rembg hardcodes.

Precedent for patching a library attribute this way: ``core.native_libs``
wraps ``cffi.FFI.dlopen``.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from core.progress import ProgressReporter

_MEGABYTE = 1024 * 1024


class ReporterProgressBar:
    """The progress-bar surface pooch drives, backed by a ProgressReporter.

    Attributes:
        total: Byte count pooch sets once it knows the content length.
        done: Bytes reported so far.
    """

    def __init__(self, reporter: ProgressReporter, label: str) -> None:
        """Initialise a bar.

        Args:
            reporter: Where progress goes.
            label: What is being downloaded, shown alongside the byte counts.
        """
        self._reporter = reporter
        self._label = label
        self.total: int | None = None
        self.done = 0

    def update(self, n: int) -> None:
        """Record *n* more bytes.

        Args:
            n: Bytes received since the last call.
        """
        self.done += n
        fraction = None if not self.total else self.done / self.total
        self._reporter.update(fraction, self._detail())

    def reset(self) -> None:
        """Start the count over; pooch does this before filling the bar."""
        self.done = 0

    def close(self) -> None:
        """Report the download complete."""
        self._reporter.finish(self._detail())

    def _detail(self) -> str:
        """Build the label with a byte count a person can read.

        Returns:
            E.g. ``"Downloading u2net weights — 42 / 176 MB"``.
        """
        done_mb = self.done / _MEGABYTE
        if not self.total:
            return f"{self._label} — {done_mb:.0f} MB"
        return f"{self._label} — {done_mb:.0f} / {self.total / _MEGABYTE:.0f} MB"


@contextmanager
def reporting_downloads(label: str) -> Iterator[None]:
    """Route any ``pooch.retrieve(progressbar=True)`` inside the block to progress events.

    A call that passes anything other than ``True`` is left alone. pooch is
    imported lazily because it arrives with rembg, and this module must not
    make it a requirement for scripts that never download anything.

    Args:
        label: Shown in the status bar while the download runs.

    Yields:
        Nothing; the patch is active for the duration of the block.
    """
    import pooch  # noqa: PLC0415

    original = pooch.retrieve

    def retrieve(*args: object, **kwargs: object) -> object:
        if kwargs.get("progressbar") is True:
            kwargs["progressbar"] = ReporterProgressBar(ProgressReporter(), label)
        return original(*args, **kwargs)

    pooch.retrieve = retrieve
    try:
        yield
    finally:
        pooch.retrieve = original
