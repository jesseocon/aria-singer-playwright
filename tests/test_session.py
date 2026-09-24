"""Unit tests for session probing helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from singer_playwright.errors import ReAuthRequiredError
from singer_playwright.session import (
    assert_authenticated,
    is_authenticated_url,
    is_login_url,
    page_looks_like_login,
)


def test_is_login_url() -> None:
    assert is_login_url("https://app.mylighthouse.com/login")
    assert not is_login_url("https://app.mylighthouse.com/hotel/123")


def test_is_authenticated_url() -> None:
    assert is_authenticated_url("https://app.mylighthouse.com/hotel/123")
    assert not is_authenticated_url("https://app.mylighthouse.com/login")


def test_page_looks_like_login_from_url() -> None:
    page = MagicMock()
    page.url = "https://app.mylighthouse.com/login"
    assert page_looks_like_login(page) is True


def test_assert_authenticated_raises() -> None:
    page = MagicMock()
    page.url = "https://app.mylighthouse.com/login"
    page.locator.return_value.count.return_value = 1
    page.locator.return_value.inner_text.return_value = "Sign in to Lighthouse"

    with pytest.raises(ReAuthRequiredError):
        assert_authenticated(page)
