"""How many bytes a run's browser moves, per host and kind of request: what a proxy would bill.

Every browser a run opens is counted unless ``ARIA_NETWORK_PROFILE=0``. When the browser closes,
one progress event (``kind: network``) reports its totals and its hosts; aria-runner adds up a
run's browsers and the console shows them with the run.

Sizes come from Chromium through Playwright's ``Request.sizes()``: request and response headers
plus each body as it crossed the network, so compressed bodies count compressed and cached ones
count nothing. WebSocket frames count their payloads. Not counted: calls a tap makes outside the
page (``context.request``), DNS, TLS handshakes and a proxy's own overhead, so a proxy's bill
runs a few percent higher than these totals.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from singer_playwright import progress

if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext, Page, Request, WebSocket

OFF_ENV = "ARIA_NETWORK_PROFILE"
# aria-runner keeps 8,000 characters of a log line; the event stays under that with room to spare.
MAX_EVENT_CHARS = 7000


def enabled() -> bool:
    return os.environ.get(OFF_ENV, "").strip().lower() not in {"0", "false", "no", "off"}


def _host(url: str) -> str | None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https", "ws", "wss"}:
        return None  # data:, blob: and the like never touch the network
    return parts.hostname or None


def _length(payload: str | bytes) -> int:
    return len(payload.encode() if isinstance(payload, str) else payload)


class NetworkProfile:
    """Counts the requests of one or more browser contexts until ``report()``."""

    def __init__(self, label: str = "browser", logger: logging.Logger | None = None) -> None:
        self.label = label
        self._logger = logger or logging.getLogger("singer_playwright")
        self._started = time.monotonic()
        self._hosts: dict[str, dict[str, Any]] = {}
        self._failed = 0
        self._reported = False

    @classmethod
    def watch(cls, context: BrowserContext, label: str, logger: logging.Logger | None = None) -> NetworkProfile | None:
        """A profile counting ``context``, or None when profiling is off."""
        if not enabled():
            return None
        profile = cls(label, logger)
        profile.attach(context)
        return profile

    def attach(self, context: BrowserContext) -> None:
        context.on("requestfinished", self._finished)
        context.on("requestfailed", self._failed_request)
        context.on("page", self._page)
        for page in context.pages:
            self._page(page)

    def _page(self, page: Page) -> None:
        page.on("websocket", self._websocket)

    def _websocket(self, socket: WebSocket) -> None:
        host = _host(socket.url)
        if host is None:
            return
        self._add(host, "websocket", requests=1)
        socket.on("framereceived", lambda payload: self._add(host, "websocket", received=_length(payload)))
        socket.on("framesent", lambda payload: self._add(host, "websocket", sent=_length(payload)))

    def _finished(self, request: Request) -> None:
        if self._reported:
            return
        host = _host(request.url)
        if host is None:
            return
        try:
            sizes = request.sizes()
        except Exception:  # noqa: BLE001 - the context may be closing; count the request without bytes
            self._add(host, request.resource_type, requests=1)
            return
        self._add(
            host,
            request.resource_type,
            requests=1,
            received=sizes["responseHeadersSize"] + sizes["responseBodySize"],
            sent=sizes["requestHeadersSize"] + sizes["requestBodySize"],
        )

    def _failed_request(self, request: Request) -> None:
        host = _host(request.url)
        if host is None or self._reported:
            return
        self._failed += 1
        self._add(host, request.resource_type, requests=1)

    def _add(self, host: str, kind: str, *, requests: int = 0, received: int = 0, sent: int = 0) -> None:
        entry = self._hosts.setdefault(host, {"host": host, "requests": 0, "received": 0, "sent": 0, "kinds": {}})
        entry["requests"] += requests
        entry["received"] += max(received, 0)
        entry["sent"] += max(sent, 0)
        counts = entry["kinds"].setdefault(kind, [0, 0])
        counts[0] += requests
        counts[1] += max(received, 0)

    def summary(self) -> dict[str, Any]:
        """Totals and every host, largest first; hosts past the event's size fold into the totals only."""
        hosts = sorted(self._hosts.values(), key=lambda h: (-h["received"] - h["sent"], h["host"]))
        out: dict[str, Any] = {
            "browser": self.label,
            "seconds": round(time.monotonic() - self._started, 1),
            "requests": sum(h["requests"] for h in hosts),
            "failed": self._failed,
            "received": sum(h["received"] for h in hosts),
            "sent": sum(h["sent"] for h in hosts),
            "hosts": [],
        }
        size = len(json.dumps(out))
        for index, host in enumerate(hosts):
            entry_size = len(json.dumps(host)) + 1
            if size + entry_size > MAX_EVENT_CHARS:
                out["hosts_folded"] = len(hosts) - index
                break
            out["hosts"].append(host)
            size += entry_size
        return out

    def report(self) -> dict[str, Any] | None:
        """Report once (an event and a readable line). Call after the context closes. Never raises."""
        if self._reported:
            return None
        self._reported = True
        try:
            data = self.summary()
            top = ", ".join(f"{h['host']} {h['received'] / 1e6:.1f} MB" for h in data["hosts"][:3])
            self._logger.info(
                "Network (%s browser): %.1f MB received, %.1f MB sent, %d requests in %.0f s%s",
                self.label,
                data["received"] / 1e6,
                data["sent"] / 1e6,
                data["requests"],
                data["seconds"],
                f"; most from {top}" if top else "",
            )
            progress.report(self._logger, "network", **data)
        except Exception:  # noqa: BLE001 - counting must never stop a run
            self._logger.debug("could not report the network profile", exc_info=True)
            return None
        return data
