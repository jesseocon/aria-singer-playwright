"""Chromium lifecycle: launch once per tap run, reuse context across streams."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Playwright


@dataclass
class BrowserConfig:
    """Runtime browser settings."""

    storage_state_path: str
    headless: bool = True
    viewport_width: int = 1600
    viewport_height: int = 1000


class BrowserRuntime:
    """Owns Playwright browser + context for the duration of a tap run."""

    def __init__(self, config: BrowserConfig) -> None:
        self._config = config
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            msg = "BrowserRuntime.start() must be called before accessing context"
            raise RuntimeError(msg)
        return self._context

    @property
    def page(self) -> Page:
        if self._page is None:
            msg = "BrowserRuntime.start() must be called before accessing page"
            raise RuntimeError(msg)
        return self._page

    def start(self) -> None:
        path = Path(self._config.storage_state_path).expanduser()
        if not path.is_file():
            msg = (
                f"storage_state not found at {path}. "
                "Run `python -m singer_playwright auth` first."
            )
            raise FileNotFoundError(msg)

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=self._config.headless)
        self._context = self._browser.new_context(
            storage_state=str(path),
            viewport={
                "width": self._config.viewport_width,
                "height": self._config.viewport_height,
            },
        )
        self._page = self._context.new_page()

    def stop(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def __enter__(self) -> BrowserRuntime:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()


def browser_session(config: BrowserConfig) -> Iterator[BrowserRuntime]:
    """Context manager yielding a started BrowserRuntime."""
    runtime = BrowserRuntime(config)
    try:
        runtime.start()
        yield runtime
    finally:
        runtime.stop()
