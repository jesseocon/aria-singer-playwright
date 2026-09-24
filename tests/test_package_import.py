"""Verify framework installs standalone (no consumer workspace)."""

from __future__ import annotations


def test_import_playwright_tap_and_stream() -> None:
    from singer_playwright.stream import PlaywrightStream
    from singer_playwright.tap import PlaywrightTap

    assert PlaywrightTap.name
    assert PlaywrightStream.__name__ == "PlaywrightStream"
