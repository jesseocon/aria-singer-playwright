"""HTTP client for an running workshop daemon."""

from __future__ import annotations

import http.client
import json
from typing import Any

from singer_playwright.workshop.runs import load_session_file


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    session = load_session_file()
    conn = http.client.HTTPConnection(session["host"], int(session["port"]), timeout=300)
    payload = json.dumps(body or {}).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    conn.request(method, path, body=payload, headers=headers)
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    data = json.loads(raw or "{}")
    if response.status >= 400 or not data.get("ok", True):
        error = data.get("error") or f"HTTP {response.status}"
        msg = f"Workshop request failed: {error}"
        raise RuntimeError(msg)
    return data


def health() -> dict[str, Any]:
    return _request("GET", "/health")


def observe(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    return _request("POST", "/observe", kwargs)


def goto(url: str, *, wait_until: str = "domcontentloaded") -> dict[str, Any]:
    return _request("POST", "/goto", {"url": url, "wait_until": wait_until})


def act(action: str, **params: Any) -> dict[str, Any]:  # noqa: ANN401
    return _request("POST", "/act", {"action": action, "params": params})


def extract(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    return _request("POST", "/extract", kwargs)


def screenshot(name: str = "screenshot") -> dict[str, Any]:
    return _request("POST", "/screenshot", {"name": name})


def recipe_save(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    return _request("POST", "/recipe/save", kwargs)


def stop() -> dict[str, Any]:
    return _request("POST", "/stop", {})
