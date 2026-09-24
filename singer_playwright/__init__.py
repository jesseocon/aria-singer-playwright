"""Shared Playwright + Singer SDK base classes for browser-backed taps."""

from singer_playwright.errors import ReAuthRequiredError, SessionInvalidError
from singer_playwright.stream import PlaywrightStream
from singer_playwright.tap import PlaywrightTap

__all__ = [
    "PlaywrightStream",
    "PlaywrightTap",
    "ReAuthRequiredError",
    "SessionInvalidError",
]
