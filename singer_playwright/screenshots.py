"""Screenshots a run keeps, so a person can see the page at the moment something went wrong.

aria-runner gives every run a folder in ``ARIA_SCREENSHOT_DIR``, uploads what lands there and
shows each image in the run's log panel next to the notice that names it. Outside a run (no
folder) nothing is saved. A screenshot never raises: it must not change how a sync ends.

Screens can show what the vendor's page shows (hotel data, the signed-in user's name). They
stay in the deployment's private bucket, like the run's log.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from singer_playwright import progress

if TYPE_CHECKING:
    from playwright.sync_api import Page

DIR_ENV = "ARIA_SCREENSHOT_DIR"
QUALITY = 60


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:60] or "screen"


def screenshot(page: Page | None, label: str, logger: logging.Logger, *, stream: str | None = None) -> str | None:
    """Save the visible page as JPEG and report a notice naming it. Returns the file name."""
    folder = os.environ.get(DIR_ENV)
    if not folder or page is None:
        return None
    try:
        if page.is_closed():
            return None
        name = f"{datetime.now(UTC):%H%M%S%f}"[:9] + f"-{_slug(label)}.jpg"
        final = Path(folder) / name
        partial = final.with_name(final.name + ".part")
        page.screenshot(path=str(partial), type="jpeg", quality=QUALITY, timeout=10_000)
        # The runner uploads only complete .jpg files, so rename into place once written.
        os.replace(partial, final)
    except Exception:  # noqa: BLE001
        logger.debug("could not take screenshot %r", label, exc_info=True)
        return None
    progress.report(logger, "notice", message=f"Screenshot: {label} ({page.url[:200]})", code="screenshot", screenshot=name, stream=stream)
    return name
