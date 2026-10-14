from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from singer_playwright.workshop.network import (
    NetworkRecorder,
    apply_query_overrides,
    endpoint_key,
    redact_headers,
    redact_url,
    summarize_shape,
)

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"


class FakeFrame:
    url = "https://spider.example.com/dashboards/day-by-day?token=abc123&asof=2026-10-01"


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self._body = body
        self.status = 200
        self.headers = {"content-type": content_type}

    def all_headers(self) -> dict[str, str]:
        return {"content-type": self.headers["content-type"], "set-cookie": "sid=secret"}

    def body(self) -> bytes:
        return self._body


class FakeRequest:
    def __init__(self, url: str, *, method: str = "GET", post: bytes | None = None, body: bytes = b"{}") -> None:
        self.url = url
        self.method = method
        self.resource_type = "xhr"
        self.frame = FakeFrame()
        self.headers = {"authorization": f"Bearer {JWT}", "accept": "application/json"}
        self.post_data_buffer = post
        self.timing = {"responseEnd": 12.5}
        self.failure = None
        self._response = FakeResponse(body)

    def all_headers(self) -> dict[str, str]:
        return {**self.headers, "cookie": "sid=secret"}

    def response(self) -> FakeResponse:
        return self._response


class FakeApiResponse:
    status = 200
    headers = {"content-type": "application/json"}

    def body(self) -> bytes:
        return b'{"rows": [1, 2]}'


class FakeApiRequest:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def fetch(self, url: str, **kwargs: Any) -> FakeApiResponse:  # noqa: ANN401
        self.calls.append({"url": url, **kwargs})
        return FakeApiResponse()


def test_redact_headers_masks_auth_and_cookies() -> None:
    redacted = redact_headers({"Authorization": "Bearer x", "Cookie": "a=b", "Accept": "json", "X-Foo": JWT})
    assert redacted["Accept"] == "json"
    assert redacted["Authorization"].startswith("<redacted sha256:")
    assert redacted["Cookie"].startswith("<redacted")
    assert redacted["X-Foo"].startswith("<redacted")


def test_redact_url_masks_token_params_and_jwts() -> None:
    url = redact_url(f"https://h/p?token=abc&asof=2026-10-01&x={JWT}")
    assert "abc" not in url
    assert JWT not in url
    assert "asof=2026-10-01" in url


def test_endpoint_key_templates_ids_and_dates() -> None:
    key = endpoint_key("get", "https://h.com/api/hotel/202158/day/2026-10-01/c0ffee1234567890abcd?x=1")
    assert key == "GET h.com/api/hotel/{n}/day/{date}/{hex}"


def test_apply_query_overrides_replaces_and_removes() -> None:
    url = apply_query_overrides("https://h/p?asof=2026-10-01&keep=1&drop=2", {"asof": "2026-10-02", "drop": None})
    assert "asof=2026-10-02" in url
    assert "keep=1" in url
    assert "drop" not in url


def test_summarize_shape_reports_types_not_values() -> None:
    shape = summarize_shape({"rows": [{"date": "2026-10-01", "adr": 1.5}], "total": None})
    assert shape == {"rows": {"list": 1, "item": {"date": "str", "adr": "float"}}, "total": "null"}


def test_recorder_persists_redacted_calls_and_catalogs(tmp_path: Path) -> None:
    recorder = NetworkRecorder(tmp_path / "network")
    recorder._on_finished(FakeRequest("https://api.example.com/v1/hotels/202158/days?asof=2026-10-01"))
    recorder.mark("change-asof")
    recorder._on_finished(
        FakeRequest(
            "https://api.example.com/v1/hotels/202158/days?asof=2026-10-02",
            body=json.dumps({"rows": [{"a": 1}]}).encode(),
        ),
    )

    persisted = (tmp_path / "network" / "calls.jsonl").read_text()
    assert JWT not in persisted
    assert "sid=secret" not in persisted
    assert "abc123" not in persisted

    catalog = recorder.catalog()
    assert catalog["endpoint_count"] == 1
    endpoint = catalog["endpoints"][0]
    assert endpoint["endpoint"] == "GET api.example.com/v1/hotels/{n}/days"
    assert endpoint["count"] == 2
    assert endpoint["query_params"]["asof"] == ["2026-10-01", "2026-10-02"]
    assert endpoint["after_marks"] == ["change-asof"]

    since = recorder.catalog(since_mark="change-asof", write=False)
    assert since["call_count"] == 1


def test_graphql_calls_are_grouped_by_operation(tmp_path: Path) -> None:
    recorder = NetworkRecorder(tmp_path / "network")
    for name, asof in (("DayByDay", "2026-10-01"), ("DayByDay", "2026-10-02"), ("Hotels", None)):
        post = json.dumps({"operationName": name, "query": f"query {name} {{ x }}", "variables": {"asof": asof}})
        recorder._on_finished(FakeRequest("https://h.com/graphql", method="POST", post=post.encode()))

    endpoints = {e["endpoint"]: e for e in recorder.catalog(write=False)["endpoints"]}
    assert set(endpoints) == {"POST h.com/graphql #DayByDay", "POST h.com/graphql #Hotels"}
    assert endpoints["POST h.com/graphql #DayByDay"]["graphql_variables"] == [
        {"asof": "2026-10-01"},
        {"asof": "2026-10-02"},
    ]


def test_replay_reuses_raw_headers_and_patches_body(tmp_path: Path) -> None:
    recorder = NetworkRecorder(tmp_path / "network")
    recorder._on_finished(
        FakeRequest(
            "https://api.example.com/v1/query?asof=2026-10-01",
            method="POST",
            post=json.dumps({"filters": {"asof": "2026-10-01"}, "limit": 10}).encode(),
        ),
    )
    api = FakeApiRequest()
    result = recorder.replay(api, 1, query={"asof": "2026-10-05"}, json_patch={"filters.asof": "2026-10-05"})

    sent = api.calls[0]
    assert "asof=2026-10-05" in sent["url"]
    assert sent["headers"]["authorization"] == f"Bearer {JWT}"
    assert "cookie" not in sent["headers"]
    assert json.loads(sent["data"])["filters"]["asof"] == "2026-10-05"
    assert result["status"] == 200
    assert result["response_shape"] == {"rows": {"list": 2, "item": "int"}}
    assert JWT not in (tmp_path / "network" / "calls.jsonl").read_text()
