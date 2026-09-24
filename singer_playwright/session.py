"""Session validity probing — fail loudly instead of scraping the login page."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from singer_playwright.errors import ReAuthRequiredError

if TYPE_CHECKING:
    from playwright.sync_api import Page

AUTHENTICATED_URL_PATTERN = re.compile(r"app\.mylighthouse\.com/(?!login)", re.IGNORECASE)
LOGIN_URL_PATTERN = re.compile(r"/login", re.IGNORECASE)


def is_login_url(url: str) -> bool:
    return bool(LOGIN_URL_PATTERN.search(url))


def is_authenticated_url(url: str) -> bool:
    return bool(AUTHENTICATED_URL_PATTERN.search(url))


def page_looks_like_login(page: Page) -> bool:
    if is_login_url(page.url):
        return True

    email_fields = page.locator('input[type="email"]')
    if email_fields.count() == 0:
        return False

    body_text = (page.locator("body").inner_text(timeout=5000) or "").lower()
    login_markers = (
        "sign in to lighthouse",
        "bringing travel & hospitality insights to light",
    )
    return any(marker in body_text for marker in login_markers)


def page_has_authenticated_shell(page: Page) -> bool:
    if page.locator('a[href*="/hotel/"]').count() > 0:
        return True
    if page.get_by_role("link", name=re.compile(r"day by day", re.I)).count() > 0:
        return True
    return False


def is_page_authenticated(page: Page) -> bool:
    if page_looks_like_login(page):
        return False

    page.wait_for_timeout(1500)

    if page_looks_like_login(page):
        return False

    if page_has_authenticated_shell(page):
        return True

    if page.locator('input[type="email"]').count() > 0:
        return False

    return is_authenticated_url(page.url)


def assert_authenticated(page: Page) -> None:
    if not is_page_authenticated(page):
        raise ReAuthRequiredError()


def probe_session(page: Page, probe_url: str, *, timeout_ms: int = 30_000) -> None:
    """Navigate to probe_url and verify the saved session is still valid."""
    page.goto(probe_url, wait_until="domcontentloaded", timeout=timeout_ms)
    assert_authenticated(page)
