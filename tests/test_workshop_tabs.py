"""Workshop follows tabs opened by clicks and records traffic while idle."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from singer_playwright.workshop.daemon import _PumpingHTTPServer
from singer_playwright.workshop.session_state import WorkshopSessionState

PAGES = {
    "/": b'<html><title>Portal</title><a id="app" href="/app" target="_blank">My app</a></html>',
    "/app": (
        b"<html><title>App</title><script>"
        b"fetch('/api/data', {method: 'POST', headers: {'Content-Type': 'application/json'},"
        b" body: JSON.stringify({operationName: 'Listing', query: 'query Listing { rows }', variables: {}})});"
        b"</script></html>"
    ),
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self._send(PAGES.get(self.path, b"missing"), "text/html")

    def do_POST(self) -> None:  # noqa: N802
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send(b'{"data": {"rows": [1, 2]}}', "application/json")


@pytest.fixture
def site() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[WorkshopSessionState]:
    monkeypatch.chdir(tmp_path)
    state = WorkshopSessionState(storage_state_path=str(tmp_path / "login.json"), fresh=True)
    try:
        state.start()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"chromium unavailable: {exc}")
    yield state
    state.stop()


def _pump_until(session: WorkshopSessionState, done: Any, seconds: float = 10) -> None:  # noqa: ANN401
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        session.pump()
        if done():
            return
        time.sleep(0.05)
    msg = "condition not met while pumping"
    raise AssertionError(msg)


def test_fresh_start_needs_no_storage_state(session: WorkshopSessionState, tmp_path: Path) -> None:
    assert not (tmp_path / "login.json").exists()
    assert session.save_storage_state()["path"] == str(tmp_path / "login.json")


def test_new_tab_becomes_active_and_traffic_is_recorded(
    session: WorkshopSessionState, site: str
) -> None:
    session.goto(site)
    portal = session.page
    # A manual click: no workshop command runs afterwards, only the idle pump.
    portal.click("#app", no_wait_after=True)

    def app_recorded() -> bool:
        calls = session._require_network().calls
        return any(c.get("graphql_operation") == "Listing" for c in calls)

    _pump_until(session, app_recorded)

    tabs = session.tabs()["tabs"]
    assert [t["active"] for t in tabs] == [False, True]
    assert tabs[1]["url"] == f"{site}/app"
    assert session.page is not portal
    opened = [s for s in session.steps if s["type"] == "tab_opened"]
    assert opened and opened[0]["opener_url"] == f"{site}/"

    session.select_tab(0)
    assert session.page is portal

    session.select_tab(1)
    session.page.close()
    assert session.page is portal
    with pytest.raises(ValueError, match="No tab 5"):
        session.select_tab(5)


def test_server_pumps_session_between_requests() -> None:
    class Spy:
        pumps = 0

        def pump(self) -> None:
            self.pumps += 1

    server = _PumpingHTTPServer.__new__(_PumpingHTTPServer)
    server.session = Spy()  # type: ignore[assignment]
    server.service_actions()
    assert server.session.pumps == 1  # type: ignore[union-attr]
