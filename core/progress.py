"""Structured progress reporting from a script back to whoever is watching.

A script runs as a subprocess, so the only channel it has to the web UI is its
own output. Ordinary lines are terminal text; a line beginning with
``::progress::`` is a machine-readable progress event instead, which the
streaming endpoint pulls out and forwards as its own SSE event rather than
printing.

A sentinel convention was deliberately avoided for *output* detection — see the
"Recent outputs panel" entry in BACKLOG.md, where a stdout heuristic covered
every script without touching any of them. Progress has no equivalent: there is
nothing to infer from, because a script that does not say how far along it is
simply is not observable. So the convention is the mechanism here.

Two rules keep it honest:

- **Emitting is throttled by the producer, not the consumer.** ffmpeg reports
  several times a second and a run can last an hour; a reporter that forwarded
  every one of those would cost more in stream traffic than the bar is worth.
- **A human at a terminal never sees a sentinel.** ``ProgressReporter`` renders
  a carriage-returned percentage to stderr for an interactive CLI run, and stays
  silent when stderr is redirected, so piping a script's output somewhere does
  not fill it with progress noise.
"""

from dataclasses import dataclass
import json
import sys
import time
from typing import TextIO

from core.invocation import is_webapp_run

SENTINEL = "::progress::"

# ffmpeg emits roughly twice a second. Forwarding every event would put
# hundreds of messages on the stream for a long transcode without telling the
# user anything a half-second-stale bar does not already tell them.
MIN_INTERVAL_SECONDS = 0.4


@dataclass(frozen=True)
class ProgressEvent:
    """One progress report from a running script.

    Attributes:
        fraction: How far along the work is, from 0.0 to 1.0, or None when the
            total is unknown. None is meaningful rather than an error — a job
            can know it has done something without knowing how much is left,
            and the bar stays indeterminate for it.
        label: Short human-readable detail, such as ``"00:12 / 01:30"``. May be
            empty.
    """

    fraction: float | None = None
    label: str = ""


def _clamp(fraction: float) -> float:
    """Constrain a fraction to the 0.0–1.0 range.

    ffmpeg's reported position can overshoot the probed duration slightly, and a
    bar wider than its track is worse than a bar that sits at full for a moment.

    Args:
        fraction: Raw fraction, possibly out of range.

    Returns:
        The fraction clamped to 0.0–1.0.
    """
    return max(0.0, min(1.0, fraction))


def encode(event: ProgressEvent) -> str:
    """Render a progress event as the single line a script should print.

    Args:
        event: The event to serialise.

    Returns:
        A ``::progress::``-prefixed line, without a trailing newline.
    """
    payload = {"fraction": event.fraction, "label": event.label}
    return SENTINEL + json.dumps(payload)


def parse(line: str) -> ProgressEvent | None:
    """Recover a progress event from a line of script output.

    Args:
        line: One line of a script's stdout, with or without trailing newline.

    Returns:
        The decoded event, or None if the line is ordinary output. A malformed
        sentinel line also returns None: a script mid-transcode should not be
        failed over a mangled progress report.
    """
    stripped = line.strip()
    if not stripped.startswith(SENTINEL):
        return None
    try:
        payload = json.loads(stripped.removeprefix(SENTINEL))
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None

    raw = payload.get("fraction")
    try:
        fraction = None if raw is None else _clamp(float(raw))
    except TypeError, ValueError:
        return None
    return ProgressEvent(fraction=fraction, label=str(payload.get("label", "")))


class ProgressReporter:
    """Emits progress for one unit of work, at a rate worth watching.

    Where the report goes depends on who started the run: a sentinel line on
    stdout for the web UI, an in-place percentage on stderr for a person at a
    terminal, nothing at all when neither is watching.

    Attributes:
        label_prefix: Prepended to every label, so a caller running several
            stages can say which one is moving.
    """

    def __init__(
        self,
        *,
        label_prefix: str = "",
        min_interval: float = MIN_INTERVAL_SECONDS,
        stream: TextIO | None = None,
        to_webapp: bool | None = None,
    ) -> None:
        """Initialise a reporter.

        Args:
            label_prefix: Text prepended to each emitted label.
            min_interval: Minimum seconds between emitted events. Updates
                arriving sooner are dropped unless they are terminal.
            stream: Where to write. Defaults to stdout for a webapp run and
                stderr for a CLI one; injectable for tests.
            to_webapp: Force sentinel or human formatting instead of detecting
                the caller. Mainly for tests.
        """
        self.label_prefix = label_prefix
        self._min_interval = min_interval
        self._to_webapp = is_webapp_run() if to_webapp is None else to_webapp
        self._stream = stream if stream is not None else (sys.stdout if self._to_webapp else sys.stderr)
        self._last_emit: float | None = None
        self._last_percent: int | None = None

    def _should_emit(self, fraction: float | None, *, force: bool) -> bool:
        """Decide whether an update is worth putting on the wire.

        Args:
            fraction: The new fraction, or None when unknown.
            force: True for a terminal update, which always goes out.

        Returns:
            True if the update should be emitted.
        """
        if force:
            return True
        now = time.monotonic()
        if self._last_emit is not None and now - self._last_emit < self._min_interval:
            return False
        # Below the throttle interval a repeated whole percent tells the user
        # nothing, and on a long job most updates are repeats.
        if fraction is not None:
            percent = int(fraction * 100)
            if percent == self._last_percent:
                return False
        return True

    def _write(self, event: ProgressEvent) -> None:
        """Write one event in the format this reporter's audience expects.

        Args:
            event: The event to write.
        """
        if self._to_webapp:
            print(encode(event), file=self._stream, flush=True)
            return
        if not self._stream.isatty():
            return
        percent = "  ??%" if event.fraction is None else f"{int(event.fraction * 100):3d}%"
        detail = f"  {event.label}" if event.label else ""
        # Carriage return rather than newline: one line that updates in place,
        # the way ffmpeg's own stats line behaves.
        print(f"\r  {percent}{detail}", end="", file=self._stream, flush=True)

    def update(self, fraction: float | None = None, label: str = "", *, force: bool = False) -> None:
        """Report current progress, subject to throttling.

        Args:
            fraction: How far along, 0.0–1.0, or None when the total is
                unknown.
            label: Short detail for this moment in the work.
            force: Emit even if the throttle would otherwise drop it.
        """
        clamped = None if fraction is None else _clamp(fraction)
        if not self._should_emit(clamped, force=force):
            return
        full_label = f"{self.label_prefix}{label}" if self.label_prefix else label
        self._write(ProgressEvent(fraction=clamped, label=full_label))
        self._last_emit = time.monotonic()
        self._last_percent = None if clamped is None else int(clamped * 100)

    def finish(self, label: str = "") -> None:
        """Report the work as complete.

        Args:
            label: Optional closing detail.
        """
        self.update(1.0, label, force=True)
        if not self._to_webapp and self._stream.isatty():
            print(file=self._stream, flush=True)
