"""Report run progress the way aria-runner reads it (progress contract v1).

A tap reports an event by logging one line that contains ``ARIA {json}``:

    ARIA {"v":1,"kind":"stream.finished","stream":"journal_lines","records":42155}

aria-runner turns these into the checklist above a run's log (see aria-runner's
docs/connector-contract.md). ``PlaywrightStream`` already reports each stream's start,
finish (with its row count) and failure; a stream adds ``progress``, ``notice`` and
``skip`` calls where a person would want to know more. Kept free of aria-runner
imports, since taps run in their own environment.
"""

from __future__ import annotations

import json
import logging
from typing import Any

VERSION = 1
MARKER = "ARIA "

# kind -> fields every event of that kind must carry (mirrors aria_runner.progress.REQUIRED)
REQUIRED: dict[str, tuple[str, ...]] = {
    "step.started": ("step",),
    "step.finished": ("step",),
    "stream.started": ("stream",),
    "stream.progress": ("stream", "done"),
    "stream.finished": ("stream",),
    "stream.skipped": ("stream", "reason"),
    "notice": ("message",),
    "warning": ("message",),
    "error": ("message",),
}


def line(kind: str, **fields: Any) -> str:
    """The log line that reports one event."""
    missing = [name for name in REQUIRED.get(kind, ()) if fields.get(name) in (None, "")]
    if kind not in REQUIRED or missing:
        msg = f"{kind} needs {', '.join(missing)}" if missing else f"unknown progress kind {kind!r}"
        raise ValueError(msg)
    event = {"v": VERSION, "kind": kind, **{k: v for k, v in fields.items() if v is not None}}
    return MARKER + json.dumps(event, separators=(",", ":"), sort_keys=True, default=str)


def report(logger: logging.Logger, kind: str, **fields: Any) -> None:
    """Log one event. Never raises: progress must not stop a sync."""
    try:
        logger.info("%s", line(kind, **fields))
    except Exception:  # noqa: BLE001
        logger.debug("could not report %s", kind, exc_info=True)
