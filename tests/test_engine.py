"""A login set to max stealth drives patchright's Google Chrome; every other run keeps Playwright."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from singer_playwright import browser
from singer_playwright.browser import BrowserConfig, BrowserRuntime, context_options, launch_chromium, max_stealth


def test_standard_unless_the_login_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    assert not max_stealth()
    monkeypatch.setenv(browser.BROWSER_ENV, "standard")
    assert not max_stealth()
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    assert max_stealth()


def test_standard_launch_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    playwright = MagicMock()
    launch_chromium(playwright, headless=True)
    kwargs = playwright.chromium.launch.call_args.kwargs
    assert kwargs["headless"] is True
    assert "channel" not in kwargs
    assert context_options(width=800, height=600) == {"viewport": {"width": 800, "height": 600}}


def test_max_stealth_launches_real_chrome_headed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    monkeypatch.delenv(browser.TIMEZONE_ENV, raising=False)
    playwright = MagicMock()
    launch_chromium(playwright, headless=True, width=1600, height=1000)
    kwargs = playwright.chromium.launch.call_args.kwargs
    assert kwargs["channel"] == "chrome"
    assert kwargs["headless"] is False
    assert "--window-size=1600,1000" in kwargs["args"]
    assert kwargs["slow_mo"] > 0
    assert "--lang=en-US" in kwargs["args"]
    assert kwargs["env"]["TZ"] == "America/Chicago"
    partitioning_off = [a for a in kwargs["args"] if a.startswith("--disable-features=")]
    assert partitioning_off and "ThirdPartyStoragePartitioning" not in partitioning_off[0]
    assert context_options() == {"no_viewport": True}
    monkeypatch.setenv(browser.TIMEZONE_ENV, "America/New_York")
    launch_chromium(playwright, headless=True)
    assert playwright.chromium.launch.call_args.kwargs["env"]["TZ"] == "America/New_York"


@patch("singer_playwright.browser.apply_stealth")
@patch("singer_playwright.browser.sync_playwright")
def test_max_stealth_skips_playwright_stealth(
    mock_sync_playwright: MagicMock, mock_apply: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    patchright_driver = MagicMock()
    with patch("patchright.sync_api.sync_playwright", return_value=patchright_driver):
        runtime = BrowserRuntime(BrowserConfig(stealth=True))
        runtime.start()
    patchright_driver.start.return_value.chromium.launch.assert_called_once()
    mock_sync_playwright.assert_not_called()
    mock_apply.assert_not_called()
    runtime.stop()


def _chrome_installed() -> bool:
    return bool(shutil.which("google-chrome")) or Path("/Applications/Google Chrome.app").exists()


@pytest.mark.skipif(not _chrome_installed(), reason="Google Chrome is not installed")
def test_max_stealth_hides_automation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    with BrowserRuntime(BrowserConfig()) as runtime:

        def answer(route) -> None:  # never leaves the machine
            route.fulfill(status=200, content_type="text/html", body="<title>t</title>")

        runtime.page.route("https://stealth.test/**", answer)
        runtime.page.goto("https://stealth.test/")
        seen = runtime.page.evaluate(
            "() => ({webdriver: navigator.webdriver, ua: navigator.userAgent,"
            " tz: Intl.DateTimeFormat().resolvedOptions().timeZone, inner: innerWidth, outer: outerWidth})"
        )
    assert not seen["webdriver"]
    assert "HeadlessChrome" not in seen["ua"]
    assert seen["tz"] == "America/Chicago"
