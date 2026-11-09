"""Human pacing: how a person's hands and attention look to the site.

A script types a whole password in one event, clicks the exact centre of a button the
instant it appears and fires requests back to back. A person types key by key, moves the
mouse there first, and stops to read. These helpers do it the person's way:

- ``type_text``: key by key with uneven gaps, after clicking into the field.
- ``click``: the mouse travels a slight curve to a random point inside the element.
- ``pause``: a short, uneven wait (log-normal, so mostly brief with the odd longer one).
- ``Pacer``: spacing between batches of data requests, with an occasional longer break.

On by default; ``ARIA_HUMANIZE=0`` turns it off (tests, local debugging), and then every
helper does the plain, instant thing.
"""

from __future__ import annotations

import math
import os
import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

ENV = "ARIA_HUMANIZE"


def enabled() -> bool:
    return os.environ.get(ENV, "").strip().lower() not in {"0", "false", "no", "off"}


def _jitter(median: float, spread: float = 0.45) -> float:
    """A log-normal duration around ``median`` seconds: mostly near it, now and then longer."""
    return max(0.0, random.lognormvariate(math.log(max(median, 0.001)), spread))


def _wait(seconds: float, page: Page | None) -> None:
    if seconds <= 0:
        return
    if page is not None:
        page.wait_for_timeout(seconds * 1000)  # keeps the browser's events flowing meanwhile
    else:
        time.sleep(seconds)


def pause(page: Page | None = None, median: float = 0.8, spread: float = 0.45) -> float:
    """Wait a person's moment. Returns the seconds waited (0 when humanizing is off)."""
    if not enabled():
        return 0.0
    seconds = min(_jitter(median, spread), median * 6)
    _wait(seconds, page)
    return seconds


def _travel(page: Page, x: float, y: float) -> None:
    """Move the mouse to (x, y) along a gentle curve, a few steps at a time."""
    start_x = random.uniform(0.2, 0.8) * (page.viewport_size or {"width": 1600})["width"]
    start_y = random.uniform(0.2, 0.8) * (page.viewport_size or {"height": 1000})["height"]
    bend_x = (start_x + x) / 2 + random.uniform(-120, 120)
    bend_y = (start_y + y) / 2 + random.uniform(-80, 80)
    points = random.randint(3, 5)
    for i in range(1, points + 1):
        t = i / points
        px = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * bend_x + t**2 * x
        py = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * bend_y + t**2 * y
        page.mouse.move(px, py, steps=random.randint(4, 9))


def click(locator: Locator, **kwargs: object) -> None:
    """Click like a person: travel to a random spot inside the element, settle, click."""
    if not enabled():
        locator.click(**kwargs)  # type: ignore[arg-type]
        return
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box is None or box["width"] < 2 or box["height"] < 2:
        locator.click(**kwargs)  # type: ignore[arg-type]
        return
    page = locator.page
    x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
    y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
    try:
        _travel(page, x, y)
    except Exception:  # noqa: BLE001 - a mouse path is a nicety; the click is what matters
        pass
    _wait(_jitter(0.12, 0.4), page)
    locator.click(position={"x": x - box["x"], "y": y - box["y"]}, delay=random.randint(40, 120), **kwargs)  # type: ignore[arg-type]


def type_text(locator: Locator, text: str) -> None:
    """Type into a field key by key with uneven gaps (``fill`` when humanizing is off)."""
    if not enabled():
        locator.fill(text)
        return
    click(locator)
    if locator.input_value():
        locator.fill("")
    page = locator.page
    for ch in text:
        locator.press_sequentially(ch)
        _wait(_jitter(0.11, 0.5), page)


class Pacer:
    """Spacing between batches of requests: an uneven gap each time, and every so often a
    longer break, the way a person stops to read a screen before asking for the next one."""

    def __init__(self, median: float = 2.0, *, break_every: int = 12, break_median: float = 12.0) -> None:
        self.median = median
        self.break_every = break_every
        self.break_median = break_median
        self._count = 0

    def wait(self, page: Page | None = None) -> float:
        """Call before each batch after the first. Returns the seconds waited."""
        if not enabled():
            return 0.0
        self._count += 1
        if self.break_every and self._count % self.break_every == 0:
            seconds = _jitter(self.break_median, 0.35)
        else:
            seconds = _jitter(self.median, 0.45)
        seconds = min(seconds, max(self.median, self.break_median) * 4)
        _wait(seconds, page)
        return seconds
