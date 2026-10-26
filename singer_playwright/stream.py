"""PlaywrightStream — extraction-only Singer streams."""

from __future__ import annotations

import sys
from abc import abstractmethod
from typing import TYPE_CHECKING

from singer_sdk.streams import Stream

from singer_playwright import progress
from singer_playwright.helpers import polite_sleep, scroll_to_load, wait_for_network_idle
from singer_playwright.tap import PlaywrightTap

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Frame, Page
    from singer_sdk.helpers.types import Context


class PlaywrightStream(Stream):
    """Stream base for browser-backed extraction.

    Subclasses implement ``extract_records``; ``get_records`` handles tap wiring,
    rate limiting and run progress: each stream reports when it starts, when it
    finishes (with its row count) and why it failed, so aria-runner can show it.
    """

    _progress_records = 0
    _progress_skipped = False

    @property
    def playwright_tap(self) -> PlaywrightTap:
        tap = self._tap
        if not isinstance(tap, PlaywrightTap):
            msg = f"{type(self).__name__} requires a PlaywrightTap instance"
            raise TypeError(msg)
        return tap

    @property
    def page(self) -> Page:
        return self.playwright_tap.page

    @override
    def get_records(self, context: Context | None) -> Iterable[dict]:
        # Partitioned streams call this once per context; the count runs across them.
        self.report("stream.started")
        try:
            self.playwright_tap.rate_limit()
            for record in self.extract_records(self.page, context):
                self._progress_records += 1
                yield record
        except Exception as exc:
            self.report("error", message=f"{type(exc).__name__}: {exc}"[:500])
            raise
        if not self._progress_skipped:
            self.report("stream.finished", records=self._progress_records)

    def report(self, kind: str, **fields: object) -> None:
        """Report a progress event for this stream (singer_playwright.progress)."""
        progress.report(self.logger, kind, stream=self.name, **fields)

    def progress(self, done: float, total: float | None = None, unit: str | None = None) -> None:
        """How far a long stream has got, e.g. ``self.progress(12, 26, "months")``."""
        self.report("stream.progress", done=done, total=total, unit=unit)

    def notice(self, message: str, *, code: str | None = None, warning: bool = False) -> None:
        """Something a person reading the run should know (shown above the log)."""
        self.report("warning" if warning else "notice", message=message, code=code)

    def skip(self, reason: str, *, code: str | None = None) -> None:
        """Mark this stream as deliberately not fetched this run, and say why."""
        self._progress_skipped = True
        self.report("stream.skipped", reason=reason, code=code)

    @abstractmethod
    def extract_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        """Yield record dicts from the authenticated page."""

    def wait_for_network_idle(self, page: Page | None = None, *, timeout_ms: int = 30_000) -> None:
        wait_for_network_idle(page or self.page, timeout_ms=timeout_ms)

    def scroll_to_load(self, page: Page | None = None, **kwargs: object) -> None:
        scroll_to_load(page or self.page, **kwargs)  # type: ignore[arg-type]

    def polite_sleep(self, seconds: float | None = None) -> None:
        if seconds is None:
            self.playwright_tap.rate_limit()
        else:
            polite_sleep(seconds)

    def get_spider_frame(self, page: Page | None = None) -> Frame | None:
        """Return the Lighthouse Spider day-by-day iframe if present."""
        target = page or self.page
        for frame in target.frames:
            if "spider.kriyarevgen.com/dashboards/day-by-day" in frame.url.lower():
                return frame
        return None
