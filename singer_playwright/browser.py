"""Chromium lifecycle: launch once per tap run, reuse context across streams."""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from singer_playwright import network, videos

if TYPE_CHECKING:
    from collections.abc import Iterator

    from playwright.sync_api import Playwright


def chromium_launch_args() -> list[str]:
    """Flags Chromium needs in Cloud Run. A virtual display still counts as headed."""
    args = ["--disable-dev-shm-usage"]
    if os.environ.get("CLOUD_RUN_JOB") or os.environ.get("K_SERVICE"):
        args.extend(["--no-sandbox", "--disable-gpu"])
    return args


# aria-runner sets ARIA_BROWSER from the run's login, so every run on one login drives the same
# browser. "max_stealth" swaps Playwright's Chromium for patchright driving Google Chrome: no
# automation leaks over the DevTools protocol, a real Chrome build, a visible window, the same
# locale and time zone on every run, and a small pause between actions. The IP stays the cloud's.
BROWSER_ENV = "ARIA_BROWSER"
MAX_STEALTH = "max_stealth"
TIMEZONE_ENV = "ARIA_BROWSER_TIMEZONE"
DEFAULT_TIMEZONE = "America/Chicago"
SLOW_MO_MS = 120
# Playwright's own --disable-features list (patchright 1.64, chromiumSwitches.ts) minus
# ThirdPartyStoragePartitioning, which a normal Chrome keeps on. Chrome keeps the last
# --disable-features it is given, so this one replaces Playwright's.
STEALTH_DISABLED_FEATURES = (
    "AvoidUnnecessaryBeforeUnloadCheckSync,DestroyProfileOnBrowserClose,DialMediaRouteProvider,"
    "GlobalMediaControls,HttpsUpgrades,LensOverlay,MediaRouter,PaintHolding,"
    "BlockOriginHeaderModificationOnRedirect,AvoidCorsURLLoaderRestartOnRedirect,Translate,"
    "AutoDeElevate,OptimizationHints,NetworkTimeServiceQuerying,AimEnabled"
)


def max_stealth() -> bool:
    return os.environ.get(BROWSER_ENV, "").strip().lower() == MAX_STEALTH


def chrome_home() -> str:
    """A writable HOME for Google Chrome, which will not start without one (its crash handler
    needs a folder there); Playwright's Chromium does not care."""
    home = os.environ.get("HOME", "")
    if home and os.access(home, os.W_OK):
        return home
    return tempfile.gettempdir()


def start_playwright(*, stealth: bool = False) -> Playwright:
    """Start the driver for this run's browser. playwright-stealth applies only to standard runs:
    its init scripts are themselves a tell, and patchright needs none of them."""
    if max_stealth():
        from patchright.sync_api import sync_playwright as patchright_playwright

        return patchright_playwright().start()
    playwright = sync_playwright().start()
    if stealth:
        apply_stealth(playwright)
    return playwright


def launch_chromium(playwright: Playwright, *, headless: bool, width: int = 1600, height: int = 1000) -> Browser:
    """Every browser a tap opens goes through here, so a login's setting reaches all of them."""
    if max_stealth():
        # Language and time zone come from Chrome's own process, not CDP overrides, so web workers
        # agree with the page.
        timezone = os.environ.get(TIMEZONE_ENV, "").strip() or DEFAULT_TIMEZONE
        return playwright.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                *chromium_launch_args(),
                f"--window-size={width},{height}",
                "--lang=en-US",
                f"--disable-features={STEALTH_DISABLED_FEATURES}",
            ],
            env={**os.environ, "TZ": timezone, "LANG": "en_US.UTF-8", "HOME": chrome_home()},
            slow_mo=SLOW_MO_MS,
        )
    return playwright.chromium.launch(headless=headless, args=chromium_launch_args())


def context_options(*, width: int = 1600, height: int = 1000) -> dict[str, object]:
    """new_context options for this run's browser (add storage_state and video on top)."""
    if max_stealth():
        # The page takes the real window's size, so screen, window and viewport agree.
        return {"no_viewport": True}
    return {"viewport": {"width": width, "height": height}}


@dataclass
class BrowserConfig:
    """Runtime browser settings."""

    storage_state_path: str | None = None
    headless: bool = True
    viewport_width: int = 1600
    viewport_height: int = 1000
    # Mask the signs of an automated browser (playwright-stealth): navigator.webdriver, headless user agent,
    # plugins, WebGL vendor and the like. Off by default; a tap turns it on per connection. Ignored when
    # the run's login is set to max stealth (ARIA_BROWSER), which drives patchright instead.
    stealth: bool = False
    # Names this browser in the run's network profile (several browsers can serve one run).
    label: str = "browser"


def stealth_platform() -> str:
    """navigator.platform for this host, so it agrees with the user agent (stealth's default is Win32)."""
    if sys.platform == "darwin":
        return "MacIntel"
    if sys.platform.startswith("win"):
        return "Win32"
    return "Linux x86_64"


def apply_stealth(playwright: Playwright) -> None:
    """Hook every browser this Playwright launches: init scripts and request headers both."""
    from playwright_stealth import Stealth

    Stealth(navigator_platform_override=stealth_platform()).hook_playwright_context(playwright)


class BrowserRuntime:
    """Owns Playwright browser + context for the duration of a tap run."""

    def __init__(self, config: BrowserConfig, logger: logging.Logger | None = None) -> None:
        self._config = config
        self._logger = logger or logging.getLogger("singer_playwright")
        # Set when the run asked for a video (aria-runner's ARIA_RECORD_VIDEO).
        self._video_dir: Path | None = None
        self._network: network.NetworkProfile | None = None
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    @property
    def context(self) -> BrowserContext:
        if self._context is None:
            msg = "BrowserRuntime.start() must be called before accessing context"
            raise RuntimeError(msg)
        return self._context

    @property
    def page(self) -> Page:
        if self._page is None:
            msg = "BrowserRuntime.start() must be called before accessing page"
            raise RuntimeError(msg)
        return self._page

    def start(self) -> None:
        storage_state: str | None = None
        if self._config.storage_state_path:
            path = Path(self._config.storage_state_path).expanduser()
            if not path.is_file():
                msg = (
                    f"storage_state not found at {path}. "
                    "Run `python -m singer_playwright auth` first."
                )
                raise FileNotFoundError(msg)
            storage_state = str(path)

        width, height = self._config.viewport_width, self._config.viewport_height
        self._playwright = start_playwright(stealth=self._config.stealth)
        if max_stealth():
            self._logger.info("Browser: patchright with Google Chrome (this login is set to max stealth)")
        self._browser = launch_chromium(self._playwright, headless=self._config.headless, width=width, height=height)
        options = context_options(width=width, height=height)
        if storage_state is not None:
            options["storage_state"] = storage_state
        self._video_dir = videos.recording_dir()
        if self._video_dir is not None:
            options["record_video_dir"] = str(self._video_dir)
            options["record_video_size"] = videos.SIZE
        self._context = self._browser.new_context(**options)
        self._network = network.NetworkProfile.watch(self._context, self._config.label, self._logger)
        self._page = self._context.new_page()

    def stop(self) -> None:
        recordings: list[Path] = []
        if self._context is not None:
            if self._video_dir is not None:
                recordings = self._recordings()
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None
        if self._video_dir is not None:
            # Playwright finishes writing each video when its page's context closes.
            videos.keep(recordings, self._logger)
            shutil.rmtree(self._video_dir, ignore_errors=True)
            self._video_dir = None
        if self._network is not None:
            self._network.report()
            self._network = None

    def _recordings(self) -> list[Path]:
        paths: list[Path] = []
        for page in self.context.pages:
            try:
                if page.video is not None:
                    paths.append(Path(page.video.path()))
            except Exception:  # noqa: BLE001 - a recording must never stop the run
                self._logger.debug("no recording for a page", exc_info=True)
        return paths

    def __enter__(self) -> BrowserRuntime:
        self.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self.stop()


def browser_session(config: BrowserConfig) -> Iterator[BrowserRuntime]:
    """Context manager yielding a started BrowserRuntime."""
    runtime = BrowserRuntime(config)
    try:
        runtime.start()
        yield runtime
    finally:
        runtime.stop()
