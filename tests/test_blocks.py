"""A refused browser is reported: rate limits and challenge pages, once per host and reason."""

from __future__ import annotations

import json
import logging

import pytest

from singer_playwright import blocks
from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.network import NetworkProfile
from singer_playwright.progress import MARKER

CHALLENGE = "<html><head><title>Just a moment...</title></head><body><script>window._cf_chl_opt={}</script></body></html>"


def _events(caplog: pytest.LogCaptureFixture) -> list[dict]:
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith(MARKER)]
    return [e for e in (json.loads(x.removeprefix(MARKER)) for x in lines) if e["kind"] == "blocked"]


def test_challenge_pages_and_rate_limits_are_reported_once(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("test-blocks")

    def answer(route) -> None:  # never leaves the machine
        url = route.request.url
        if url.endswith("/challenge"):
            route.fulfill(status=403, content_type="text/html", body=CHALLENGE)
        elif url.endswith("/api"):
            route.fulfill(status=429, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="text/html", body="<p>fine</p>")

    with caplog.at_level(logging.INFO, logger="test-blocks"), BrowserRuntime(BrowserConfig()) as runtime:
        NetworkProfile.watch(runtime.context, "test", logger)
        page = runtime.page
        page.route("https://site.test/**", answer)
        page.goto("https://site.test/")
        page.goto("https://site.test/challenge")
        page.goto("https://site.test/challenge")
        page.evaluate("() => fetch('/api')")
        page.evaluate("() => fetch('/api')")
    events = _events(caplog)
    assert sorted((e["reason"], e.get("vendor")) for e in events) == [("challenge", "cloudflare"), ("rate_limited", None)]


def test_markers() -> None:
    assert blocks.challenge_vendor(200, {"cf-mitigated": "challenge"}, "") == "cloudflare"
    assert blocks.challenge_vendor(403, {"x-datadome": "1"}, "") == "datadome"
    assert blocks.challenge_vendor(200, {}, "<p>an ordinary page</p>") is None
