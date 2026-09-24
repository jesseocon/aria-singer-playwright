"""Unit tests for browser lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from singer_playwright.browser import BrowserConfig, BrowserRuntime


def test_start_requires_storage_state(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    runtime = BrowserRuntime(BrowserConfig(storage_state_path=str(missing)))

    with pytest.raises(FileNotFoundError, match="storage_state not found"):
        runtime.start()


def test_teardown_is_safe_without_start() -> None:
    runtime = BrowserRuntime(BrowserConfig(storage_state_path="unused.json"))
    runtime.stop()


@patch("singer_playwright.browser.sync_playwright")
def test_start_launches_browser(mock_sync_playwright: MagicMock, tmp_path: Path) -> None:
    state_file = tmp_path / "storage_state.json"
    state_file.write_text('{"cookies": [], "origins": []}', encoding="utf-8")

    playwright = MagicMock()
    browser = MagicMock()
    context = MagicMock()
    page = MagicMock()

    mock_sync_playwright.return_value.start.return_value = playwright
    playwright.chromium.launch.return_value = browser
    browser.new_context.return_value = context
    context.new_page.return_value = page

    runtime = BrowserRuntime(BrowserConfig(storage_state_path=str(state_file)))
    runtime.start()

    playwright.chromium.launch.assert_called_once()
    browser.new_context.assert_called_once()
    context.new_page.assert_called_once()

    runtime.stop()
    context.close.assert_called_once()
    browser.close.assert_called_once()
    playwright.stop.assert_called_once()
