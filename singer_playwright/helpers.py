"""Lazy-load and wait helpers for Playwright streams."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Locator, Page


def wait_for_selector(
    target: Page | Frame,
    selector: str,
    *,
    timeout_ms: int = 30_000,
    state: str = "visible",
) -> Locator:
    return target.wait_for_selector(selector, timeout=timeout_ms, state=state)  # type: ignore[arg-type]


def scroll_to_load(
    page: Page,
    *,
    scroll_pause_seconds: float = 0.5,
    max_scrolls: int = 20,
) -> None:
    """Scroll down repeatedly until the page height stabilizes."""
    last_height = 0
    for _ in range(max_scrolls):
        height = page.evaluate("() => document.body.scrollHeight")
        if height == last_height:
            return
        last_height = height
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(scroll_pause_seconds)


def wait_for_network_idle(page: Page, *, timeout_ms: int = 30_000) -> None:
    page.wait_for_load_state("networkidle", timeout=timeout_ms)


def polite_sleep(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)
