"""A login with its own proxy: every browser leaves through it, or the run stops."""

from __future__ import annotations

import base64
import http.server
import json
import logging
import shutil
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from singer_playwright import browser
from singer_playwright.browser import (
    BrowserConfig,
    BrowserRuntime,
    context_options,
    launch_chromium,
    proxy_settings,
    start_playwright,
)
from singer_playwright.errors import ProxyError, ProxyMismatch, ProxyUnavailable

if TYPE_CHECKING:
    from collections.abc import Iterator

USER, PASSWORD = "user-sp1", "s3cret:p@ss"
EXIT_IP = "203.0.113.7"
# Only the proxy knows this host, so a browser that skipped the proxy could not answer.
CHECK_URL = "http://exit-ip.test/json"


class _Proxy(http.server.BaseHTTPRequestHandler):
    """A forward proxy that wants a password and answers the exit IP check itself."""

    seen: list[str]
    exit_ip = EXIT_IP

    def do_GET(self) -> None:  # noqa: N802
        expected = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        if self.headers.get("Proxy-Authorization") != expected:
            self.send_response(407)
            self.send_header("Proxy-Authenticate", 'Basic realm="proxy"')
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.seen.append(self.path)
        body = json.dumps({"ip": self.exit_ip}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def proxy(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Proxy]]:
    handler = type("Handler", (_Proxy,), {"seen": []})
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    monkeypatch.setattr(browser, "IP_CHECK_URLS", (CHECK_URL,))
    monkeypatch.setattr(browser, "IP_CHECK_TIMEOUT_MS", 10_000)
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    monkeypatch.setenv(browser.PROXY_ENV, f"http://{USER}:s3cret%3Ap%40ss@127.0.0.1:{port}")
    yield handler
    server.shutdown()


def test_no_proxy_unless_the_login_has_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.PROXY_ENV, raising=False)
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    assert proxy_settings() is None
    playwright = MagicMock()
    launch_chromium(playwright, headless=True)
    assert "proxy" not in playwright.chromium.launch.call_args.kwargs
    playwright.chromium.launch.return_value.new_context.assert_not_called()


def test_proxy_url_becomes_playwrights_option(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.PROXY_ENV, "http://user-1:p%40ss@isp.example.net:10001")
    assert proxy_settings() == {"server": "http://isp.example.net:10001", "username": "user-1", "password": "p@ss"}


@pytest.mark.parametrize("value", ["http://user:secret@host-without-port", "http://user:secret@host:notaport"])
def test_bad_proxy_url_stops_without_echoing_it(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(browser.PROXY_ENV, value)
    with pytest.raises(ProxyUnavailable) as caught:
        proxy_settings()
    assert "secret" not in str(caught.value)
    assert caught.value.retryable is False


@pytest.mark.parametrize("engine", ["standard", "max_stealth"])
def test_both_engines_get_the_proxy(monkeypatch: pytest.MonkeyPatch, engine: str) -> None:
    monkeypatch.setenv(browser.BROWSER_ENV, engine)
    monkeypatch.setenv(browser.PROXY_ENV, "http://u:p@isp.example.net:10001")
    monkeypatch.setenv(browser.PROXY_EXPECTED_IP_ENV, EXIT_IP)
    playwright = MagicMock()
    page = playwright.chromium.launch.return_value.new_context.return_value.new_page.return_value
    page.goto.return_value.ok = True
    page.goto.return_value.text.return_value = json.dumps({"ip": EXIT_IP})
    launch_chromium(playwright, headless=True)
    proxy = playwright.chromium.launch.call_args.kwargs["proxy"]
    assert proxy == {"server": "http://isp.example.net:10001", "username": "u", "password": "p"}


def test_mismatch_closes_the_browser_and_names_no_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    monkeypatch.setenv(browser.PROXY_ENV, "http://u:hunter2@isp.example.net:10001")
    monkeypatch.setenv(browser.PROXY_EXPECTED_IP_ENV, "198.51.100.1")
    playwright = MagicMock()
    launched = playwright.chromium.launch.return_value
    page = launched.new_context.return_value.new_page.return_value
    page.goto.return_value.ok = True
    page.goto.return_value.text.return_value = "34.1.2.3\n"
    with pytest.raises(ProxyMismatch) as caught:
        launch_chromium(playwright, headless=True)
    assert "34.1.2.3" in str(caught.value) and "198.51.100.1" in str(caught.value)
    assert "hunter2" not in str(caught.value)
    launched.close.assert_called_once()


def test_falls_back_to_the_next_ip_service(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    good = MagicMock(ok=True)
    good.text.return_value = EXIT_IP
    page.goto.side_effect = [RuntimeError("net::ERR_TUNNEL_CONNECTION_FAILED"), good]
    assert browser.exit_ip(page, logging.getLogger("test")) == EXIT_IP
    assert [c.args[0] for c in page.goto.call_args_list] == list(browser.IP_CHECK_URLS)


def test_standard_engine_takes_the_logins_time_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.BROWSER_ENV, raising=False)
    monkeypatch.delenv(browser.TIMEZONE_ENV, raising=False)
    assert "timezone_id" not in context_options()
    monkeypatch.setenv(browser.TIMEZONE_ENV, "America/New_York")
    assert context_options()["timezone_id"] == "America/New_York"
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    assert "timezone_id" not in context_options()  # Chrome's own TZ, set at launch


# Real Chromium through a real (local) proxy from here on.


def test_browser_leaves_through_the_proxy(proxy: type[_Proxy], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.PROXY_EXPECTED_IP_ENV, EXIT_IP)
    monkeypatch.setenv(browser.TIMEZONE_ENV, "America/New_York")
    with BrowserRuntime(BrowserConfig()) as runtime:
        assert proxy.seen == [CHECK_URL]  # the check, with the proxy's password
        response = runtime.page.goto(CHECK_URL)
        assert response is not None and json.loads(response.text())["ip"] == EXIT_IP
        assert runtime.page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone") == "America/New_York"


def test_wrong_exit_ip_fails_the_launch(proxy: type[_Proxy], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.PROXY_EXPECTED_IP_ENV, "198.51.100.1")
    playwright = start_playwright()
    try:
        with pytest.raises(ProxyMismatch):
            launch_chromium(playwright, headless=True)
    finally:
        playwright.stop()


def test_proxy_down_fails_the_launch(proxy: type[_Proxy], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.PROXY_EXPECTED_IP_ENV, raising=False)
    monkeypatch.setenv(browser.PROXY_ENV, "http://u:p@127.0.0.1:9")  # nothing listens there
    monkeypatch.setattr(browser, "IP_CHECK_TIMEOUT_MS", 5_000)
    playwright = start_playwright()
    try:
        with pytest.raises(ProxyUnavailable) as caught:
            launch_chromium(playwright, headless=True)
    finally:
        playwright.stop()
    assert isinstance(caught.value, ProxyError) and caught.value.retryable is False


def test_wrong_password_is_a_proxy_that_does_not_answer(proxy: type[_Proxy], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(browser.PROXY_EXPECTED_IP_ENV, raising=False)
    port = browser.proxy_settings()["server"].rsplit(":", 1)[1]  # type: ignore[index]
    monkeypatch.setenv(browser.PROXY_ENV, f"http://{USER}:wrong@127.0.0.1:{port}")
    playwright = start_playwright()
    try:
        with pytest.raises(ProxyUnavailable):
            launch_chromium(playwright, headless=True)
    finally:
        playwright.stop()
    assert proxy.seen == []


@pytest.mark.skipif(not (shutil.which("google-chrome") or Path("/Applications/Google Chrome.app").exists()), reason="Google Chrome is not installed")
def test_max_stealth_leaves_through_the_proxy(proxy: type[_Proxy], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(browser.BROWSER_ENV, "max_stealth")
    monkeypatch.setenv(browser.PROXY_EXPECTED_IP_ENV, EXIT_IP)
    monkeypatch.setenv(browser.TIMEZONE_ENV, "America/New_York")
    with BrowserRuntime(BrowserConfig()) as runtime:
        assert proxy.seen[0] == CHECK_URL  # Chrome asks for a favicon too
        assert runtime.page.evaluate("Intl.DateTimeFormat().resolvedOptions().timeZone") == "America/New_York"
