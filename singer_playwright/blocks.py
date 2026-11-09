"""Signs that a site refused the browser: rate limits and bot-challenge pages.

Every context a tap opens is watched (``NetworkProfile.watch`` and ``attach`` start it). A
429 on any request, or a page whose HTML or headers carry a known challenge marker, is a
refusal. Each one is reported once per host and reason as a ``blocked`` progress event, with
a screenshot of the page when there is one. aria-runner treats a failed run that saw a
refusal as blocked rather than transient: it cools the login down instead of retrying, since
knocking again is what gets an account or IP flagged. A run that succeeded despite one
carries it as a warning.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from singer_playwright import progress

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Response

# Text in a challenged page's HTML -> who served the challenge.
BODY_MARKERS: tuple[tuple[str, str], ...] = (
    ("_cf_chl_opt", "cloudflare"),
    ("cf-challenge", "cloudflare"),
    ("Attention Required! | Cloudflare", "cloudflare"),
    ("captcha-delivery.com", "datadome"),
    ("px-captcha", "perimeterx"),
    ("_pxCaptcha", "perimeterx"),
    ("Pardon Our Interruption", "imperva"),
    ("Incapsula incident ID", "imperva"),
    ("errors.edgesuite.net", "akamai"),
    ("/_sec/cp_challenge/", "akamai"),
    ("hcaptcha.com/captcha", "captcha"),
    ("www.google.com/recaptcha", "captcha"),
)
# Pages worth reading for markers: challenge pages are small, data pages can be large.
MAX_BODY = 512_000
# Statuses a challenge or refusal page comes back with.
REFUSAL_STATUSES = frozenset({401, 403, 405, 429, 503})


def _host(url: str) -> str | None:
    try:
        return urlsplit(url).hostname or None
    except ValueError:
        return None


def challenge_vendor(status: int, headers: dict[str, str], body: str) -> str | None:
    """Who challenged this page, or None when it doesn't look like a challenge."""
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "cloudflare"
    if status in REFUSAL_STATUSES and "x-datadome" in headers:
        return "datadome"
    for marker, vendor in BODY_MARKERS:
        if marker in body:
            return vendor
    if status == 403 and "AkamaiGHost" in headers.get("server", "") and "Reference&#32;&#35;" in body:
        return "akamai"
    return None


class BlockWatch:
    """Watches one browser context for refusals; reports each host and reason once."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("singer_playwright")
        self._seen: set[tuple[str, str]] = set()
        self.blocks: list[dict[str, object]] = []

    def attach(self, context: BrowserContext) -> None:
        context.on("response", self._response)

    def _response(self, response: Response) -> None:
        try:
            self._check(response)
        except Exception:  # noqa: BLE001 - watching must never break the run
            self._logger.debug("block check failed", exc_info=True)

    def _check(self, response: Response) -> None:
        host = _host(response.url)
        if host is None:
            return
        status = response.status
        if status == 429:
            self._blocked(host, "rate_limited", status, None, response)
            return
        request = response.request
        if request.resource_type != "document":
            return
        headers = {k.lower(): v for k, v in response.headers.items()}
        if status not in REFUSAL_STATUSES and "cf-mitigated" not in headers:
            # A 200 page is read only when it is small enough to be an interstitial.
            length = headers.get("content-length")
            if length is None or not length.isdigit() or int(length) > 20_000:
                return
        try:
            body = response.text()[:MAX_BODY]
        except Exception:  # noqa: BLE001 - redirects and closed pages have no body
            body = ""
        vendor = challenge_vendor(status, headers, body)
        if vendor is not None:
            self._blocked(host, "challenge", status, vendor, response)

    def _blocked(self, host: str, reason: str, status: int, vendor: str | None, response: Response) -> None:
        if (host, reason) in self._seen:
            return
        self._seen.add((host, reason))
        block = {"host": host, "reason": reason, "status": status, "vendor": vendor}
        self.blocks.append(block)
        shot = None
        if reason == "challenge":
            from singer_playwright import screenshots

            try:
                shot = screenshots.screenshot(response.frame.page, f"Blocked by {vendor} on {host}", self._logger)
            except Exception:  # noqa: BLE001
                shot = None
        progress.report(
            self._logger,
            "blocked",
            host=host,
            reason=reason,
            status=status,
            vendor=vendor,
            screenshot=shot,
            message=f"{host} refused the browser ({vendor or reason}, HTTP {status})",
        )


def watch(context: BrowserContext, logger: logging.Logger | None = None) -> BlockWatch:
    """Start watching ``context`` for refusals."""
    watcher = BlockWatch(logger)
    watcher.attach(context)
    return watcher
