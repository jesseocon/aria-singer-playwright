"""PlaywrightStream — extraction-only Singer streams."""

from __future__ import annotations

import sys
from abc import abstractmethod
from typing import TYPE_CHECKING

from singer_sdk.streams import Stream

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

    Subclasses implement ``extract_records``; ``get_records`` handles tap wiring
    and rate limiting.
    """

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
        self.playwright_tap.rate_limit()
        yield from self.extract_records(self.page, context)

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
