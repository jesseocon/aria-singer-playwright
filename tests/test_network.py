import gzip
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.network import MAX_EVENT_CHARS, NetworkProfile
from singer_playwright.progress import MARKER

# 200 KB of script that gzips to a few KB: the profile must count what crossed the network.
SCRIPT = ("var x = 'aria network profile';\n" * 6500).encode()
SCRIPT_GZ = gzip.compress(SCRIPT)
PAGE = b"<html><body><script src='/app.js'></script><img src='/missing.png'></body></html>"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            body, headers = PAGE, {"Content-Type": "text/html"}
        elif self.path == "/app.js":
            body, headers = SCRIPT_GZ, {"Content-Type": "application/javascript", "Content-Encoding": "gzip"}
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args: object) -> None:
        pass


@pytest.fixture
def site():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _events(caplog) -> list[dict]:
    return [json.loads(r.getMessage().removeprefix(MARKER)) for r in caplog.records if r.getMessage().startswith(MARKER)]


def test_a_browser_reports_the_bytes_it_moved_per_host_and_kind(site, monkeypatch, caplog) -> None:
    monkeypatch.delenv("ARIA_NETWORK_PROFILE", raising=False)
    logger = logging.getLogger("test-network")
    with caplog.at_level(logging.INFO, logger="test-network"):
        with BrowserRuntime(BrowserConfig(storage_state_path=None, label="tap"), logger) as runtime:
            runtime.page.goto(site + "/", wait_until="load")
    [event] = [e for e in _events(caplog) if e["kind"] == "network"]
    assert event["browser"] == "tap"
    [host] = event["hosts"]
    assert host["host"] == "127.0.0.1"
    assert set(host["kinds"]) >= {"document", "script", "image"}
    script_requests, script_bytes = host["kinds"]["script"]
    assert script_requests == 1
    # Compressed size plus headers, nowhere near the 200 KB the page unpacked.
    assert len(SCRIPT_GZ) < script_bytes < len(SCRIPT_GZ) + 2000
    assert event["received"] == host["received"] >= len(PAGE) + len(SCRIPT_GZ)
    assert event["sent"] > 0 and event["requests"] == host["requests"] >= 3
    assert any("Network (tap browser)" in r.getMessage() for r in caplog.records)


def test_profiling_can_be_turned_off(site, monkeypatch, caplog) -> None:
    monkeypatch.setenv("ARIA_NETWORK_PROFILE", "0")
    logger = logging.getLogger("test-network-off")
    with caplog.at_level(logging.INFO, logger="test-network-off"):
        with BrowserRuntime(BrowserConfig(storage_state_path=None), logger) as runtime:
            runtime.page.goto(site + "/", wait_until="load")
    assert not [e for e in _events(caplog) if e["kind"] == "network"]


def test_the_event_fits_a_log_line_and_says_how_many_hosts_it_folded() -> None:
    profile = NetworkProfile("tap")
    for index in range(400):
        profile._add(f"host-{index:03d}.cdn.example.com", "script", requests=1, received=1000 + index)
    data = profile.summary()
    assert len(json.dumps(data)) <= MAX_EVENT_CHARS
    assert data["hosts_folded"] == 400 - len(data["hosts"]) > 0
    assert data["received"] == sum(1000 + i for i in range(400))
    assert data["hosts"][0]["host"] == "host-399.cdn.example.com"


def test_report_happens_once() -> None:
    profile = NetworkProfile("tap")
    assert profile.report() is not None
    assert profile.report() is None
