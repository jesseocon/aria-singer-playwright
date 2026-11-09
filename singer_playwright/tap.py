"""PlaywrightTap — one Chromium per Singer tap run."""

from __future__ import annotations

import random
import sys
from typing import TYPE_CHECKING, ClassVar

from singer_sdk import Tap
from singer_sdk import typing as th

from singer_playwright import human
from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.login import apply_credentials
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
            "stealth",
            th.BooleanType(nullable=False),
            title="Stealth",
            description="Mask the signs of an automated browser (playwright-stealth)",
            default=False,
        ),
        th.Property(
            "rate_limit_seconds",
            th.NumberType(nullable=False),
            title="Rate Limit Seconds",
            description="Minimum seconds between page actions",
            default=5.0,
        ),
        th.Property(
            "auth_method",
            th.StringType(nullable=False),
            allowed_values=["storage_state", "password"],
            title="Auth Method",
            description="storage_state replays a saved login. password types credentials in this browser.",
            default="storage_state",
        ),
        th.Property(
            "login_url",
            th.StringType(nullable=True),
            title="Login URL",
            description="Page to open when auth_method is password",
        ),
        th.Property(
            "username",
            th.StringType(nullable=True),
            secret=True,
            title="Username",
            description="Site username. Used when auth_method is password.",
        ),
        th.Property(
            "password",
            th.StringType(nullable=True),
            secret=True,
            title="Password",
            description="Site password. Used when auth_method is password.",
        ),
    ).to_dict()

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._browser_runtime: BrowserRuntime | None = None
        self._session_verified = False

    def _ensure_browser_started(self) -> None:
        if self._browser_runtime is not None:
            return

        auth_method = self.config.get("auth_method", "storage_state")
        if auth_method == "password":
            self._start_with_password()
            return

        config = BrowserConfig(
            storage_state_path=self.config["storage_state_path"],
            headless=bool(self.config.get("headless", True)),
            stealth=bool(self.config.get("stealth", False)),
        )
        self._browser_runtime = BrowserRuntime(config, self.logger)
        self._browser_runtime.start()
        if not self._session_verified:
            probe_session(
                self._browser_runtime.page,
                self.config.get("session_probe_url") or self.config["base_url"],
            )
            self._session_verified = True

    def _start_with_password(self) -> None:
        username = self.config.get("username")
        password = self.config.get("password")
        login_url = self.config.get("login_url")
        if not username or not password or not login_url:
            msg = "auth_method password requires username, password, and login_url"
            raise ValueError(msg)
        config = BrowserConfig(
            storage_state_path=None,
            headless=bool(self.config.get("headless", True)),
            stealth=bool(self.config.get("stealth", False)),
        )
        self._browser_runtime = BrowserRuntime(config, self.logger)
        self._browser_runtime.start()
        apply_credentials(
            self._browser_runtime.page,
            username=str(username),
            password=str(password),
            login_url=str(login_url),
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
        """Wait about ``rate_limit_seconds`` between page actions: unevenly, with a longer
        break now and then, the way a person works (singer_playwright.human)."""
        from singer_playwright.helpers import polite_sleep

        seconds = float(self.config.get("rate_limit_seconds", 0))
        if seconds <= 0:
            return
        if not human.enabled():
            polite_sleep(seconds)
            return
        pacer = getattr(self, "_pacer", None)
        if pacer is None or pacer.median != seconds:
            pacer = human.Pacer(seconds, break_every=random.randint(10, 16), break_median=seconds * 5)
            self._pacer = pacer
        try:
            page = self.page if getattr(self, "_browser_runtime", None) is not None else None
        except Exception:  # noqa: BLE001 - no open page: wait without one
            page = None
        pacer.wait(page)
