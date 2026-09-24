"""PlaywrightTap — one Chromium per Singer tap run."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, ClassVar

from singer_sdk import Tap
from singer_sdk import typing as th

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.session import probe_session

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from playwright.sync_api import Page


class PlaywrightTap(Tap):
    """Base tap that launches Chromium once and validates storage_state before sync."""

    name: ClassVar[str] = "tap-playwright"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "storage_state_path",
            th.StringType(nullable=False),
            required=True,
            secret=True,
            title="Storage State Path",
            description="Path to Playwright storage_state.json saved after manual login",
        ),
        th.Property(
            "base_url",
            th.StringType(nullable=False),
            title="Base URL",
            description="Site base URL",
            default="https://example.com",
        ),
        th.Property(
            "session_probe_url",
            th.StringType(nullable=False),
            title="Session Probe URL",
            description="URL hit to verify the session before extraction",
            default="https://example.com/",
        ),
        th.Property(
            "headless",
            th.BooleanType(nullable=False),
            title="Headless",
            description="Run Chromium headless",
            default=True,
        ),
        th.Property(
            "rate_limit_seconds",
            th.NumberType(nullable=False),
            title="Rate Limit Seconds",
            description="Minimum seconds between page actions",
            default=5.0,
        ),
    ).to_dict()

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._browser_runtime: BrowserRuntime | None = None
        self._session_verified = False

    def _ensure_browser_started(self) -> None:
        if self._browser_runtime is not None:
            return

        config = BrowserConfig(
            storage_state_path=self.config["storage_state_path"],
            headless=bool(self.config.get("headless", True)),
        )
        self._browser_runtime = BrowserRuntime(config)
        self._browser_runtime.start()
        if not self._session_verified:
            probe_session(
                self._browser_runtime.page,
                self.config.get("session_probe_url") or self.config["base_url"],
            )
            self._session_verified = True

    @property
    def browser(self) -> BrowserRuntime:
        self._ensure_browser_started()
        return self._browser_runtime  # type: ignore[return-value]

    @property
    def page(self) -> Page:
        return self.browser.page

    @override
    def setup(self) -> None:
        super().setup()
        self._ensure_browser_started()

    @override
    def teardown(self) -> None:
        if self._browser_runtime is not None:
            self._browser_runtime.stop()
            self._browser_runtime = None
            self._session_verified = False
        super().teardown()

    def rate_limit(self) -> None:
        from singer_playwright.helpers import polite_sleep

        polite_sleep(float(self.config.get("rate_limit_seconds", 0)))
