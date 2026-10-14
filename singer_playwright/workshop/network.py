"""Network capture for workshop sessions: record, catalog, and replay page API calls."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

DEFAULT_RESOURCE_TYPES = frozenset({"xhr", "fetch", "eventsource"})

SECRET_HEADER_RE = re.compile(r"authorization|cookie|token|secret|session|csrf|xsrf|api[-_]?key|signature", re.I)
SECRET_PARAM_RE = re.compile(r"token|secret|session|signature|^sig$|api[-_]?key|auth|password|jwt", re.I)
JWT_RE = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]*$")
TEXT_CONTENT_RE = re.compile(r"json|text|xml|javascript|graphql|x-www-form-urlencoded", re.I)

# Headers the browser or APIRequestContext sets itself; copying them breaks replays.
REPLAY_DROP_HEADERS = frozenset({"cookie", "content-length", "host", "connection", "accept-encoding"})

_SEGMENT_TEMPLATES = (
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "{date}"),
    (re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I), "{uuid}"),
    (re.compile(r"^\d+$"), "{n}"),
    (re.compile(r"^[0-9a-f]{16,}$", re.I), "{hex}"),
    (re.compile(r"^c[a-z0-9]{20,}$"), "{cuid}"),
    (re.compile(r"^[A-Za-z0-9_-]{40,}={0,2}$"), "{b64}"),
)


def mask_secret(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"<redacted sha256:{digest} len={len(value)}>"


def is_secret_value(name: str, value: str, *, name_re: re.Pattern[str]) -> bool:
    return bool(name_re.search(name)) or bool(JWT_RE.match(value.strip()))


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        name: mask_secret(value) if is_secret_value(name, value, name_re=SECRET_HEADER_RE) else value
        for name, value in headers.items()
    }


def redact_query(query: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [
        (name, mask_secret(value) if is_secret_value(name, value, name_re=SECRET_PARAM_RE) else value)
        for name, value in query
    ]


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    query = redact_query(parse_qsl(parsed.query, keep_blank_values=True))
    return urlunparse(parsed._replace(query=urlencode(query)))


def path_template(path: str) -> str:
    segments = []
    for segment in path.split("/"):
        for pattern, replacement in _SEGMENT_TEMPLATES:
            if segment and pattern.match(segment):
                segment = replacement
                break
        segments.append(segment)
    return "/".join(segments) or "/"


def endpoint_key(method: str, url: str) -> str:
    parsed = urlparse(url)
    return f"{method.upper()} {parsed.netloc}{path_template(parsed.path)}"


def summarize_shape(value: Any, *, depth: int = 0, max_depth: int = 5, max_keys: int = 60) -> Any:  # noqa: ANN401
    """Compact type skeleton of a JSON value (keys and types, not data)."""
    if depth >= max_depth:
        return "…"
    if isinstance(value, dict):
        keys = list(value.keys())
        shape = {
            str(key): summarize_shape(value[key], depth=depth + 1, max_depth=max_depth, max_keys=max_keys)
            for key in keys[:max_keys]
        }
        if len(keys) > max_keys:
            shape["…"] = f"+{len(keys) - max_keys} keys"
        return shape
    if isinstance(value, list):
        if not value:
            return {"list": 0}
        return {
            "list": len(value),
            "item": summarize_shape(value[0], depth=depth + 1, max_depth=max_depth, max_keys=max_keys),
        }
    if value is None:
        return "null"
    return type(value).__name__


def parse_json_bytes(body: bytes) -> Any:  # noqa: ANN401
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


_GRAPHQL_NAME_RE = re.compile(r"\b(query|mutation|subscription)\s+(\w+)")


def graphql_operation(body: Any) -> str | None:  # noqa: ANN401
    if not isinstance(body, dict) or "query" not in body:
        return None
    name = body.get("operationName")
    if name:
        return str(name)
    match = _GRAPHQL_NAME_RE.search(str(body.get("query") or ""))
    return match.group(2) if match else "anonymous"


def _body_extension(content_type: str) -> str:
    if "json" in content_type:
        return "json"
    if "html" in content_type:
        return "html"
    if "xml" in content_type:
        return "xml"
    return "txt"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _set_dotted(target: dict[str, Any], dotted: str, value: Any) -> None:  # noqa: ANN401
    parts = dotted.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def apply_query_overrides(url: str, overrides: dict[str, Any]) -> str:
    """Replace query params by name; a value of None removes the param."""
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    remaining = [(k, v) for k, v in query if k not in overrides]
    for name, value in overrides.items():
        if value is None:
            continue
        values = value if isinstance(value, list) else [value]
        remaining.extend((name, str(v)) for v in values)
    return urlunparse(parsed._replace(query=urlencode(remaining)))


class NetworkRecorder:
    """Captures page API traffic into ``<run_dir>/network``.

    Persisted call records and catalogs are redacted. Raw request headers and
    bodies stay in memory only so ``replay`` can reuse the page's own auth.
    """

    def __init__(
        self,
        out_dir: Path,
        *,
        resource_types: Iterable[str] = DEFAULT_RESOURCE_TYPES,
        max_body_bytes: int = 10_000_000,
    ) -> None:
        self.out_dir = out_dir
        self.bodies_dir = out_dir / "bodies"
        self.bodies_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(out_dir, 0o700)
        os.chmod(self.bodies_dir, 0o700)
        self.calls_path = out_dir / "calls.jsonl"
        self.resource_types = frozenset(resource_types)
        self.max_body_bytes = max_body_bytes
        self.calls: list[dict[str, Any]] = []
        self.marks: list[dict[str, Any]] = []
        self.seq = 0
        self._raw: dict[int, dict[str, Any]] = {}

    def attach(self, context: Any) -> None:  # noqa: ANN401
        context.on("requestfinished", self._on_finished)
        context.on("requestfailed", self._on_failed)

    def _append(self, entry: dict[str, Any]) -> None:
        with self.calls_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, default=str) + "\n")

    def _write_body(self, name: str, body: bytes) -> str:
        path = self.bodies_dir / name
        path.write_bytes(body)
        os.chmod(path, 0o600)
        return str(path)

    def mark(self, label: str) -> dict[str, Any]:
        entry = {"type": "mark", "label": label, "after_seq": self.seq, "at": _now()}
        self.marks.append(entry)
        self._append(entry)
        return entry

    def _next_seq(self) -> int:
        # Handlers re-enter while blocked on Playwright calls, so take the seq before any of them.
        self.seq += 1
        return self.seq

    def _base_entry(self, request: Any, seq: int) -> dict[str, Any]:  # noqa: ANN401
        try:
            frame_url = request.frame.url
        except Exception:  # noqa: BLE001 - service worker requests have no frame
            frame_url = None
        try:
            headers = request.all_headers()
        except Exception:  # noqa: BLE001
            headers = dict(request.headers)
        post_data = request.post_data_buffer
        self._raw[seq] = {
            "method": request.method,
            "url": request.url,
            "headers": headers,
            "post_data": post_data,
        }
        parsed = urlparse(request.url)
        entry: dict[str, Any] = {
            "type": "call",
            "seq": seq,
            "at": _now(),
            "resource_type": request.resource_type,
            "method": request.method,
            "endpoint": endpoint_key(request.method, request.url),
            "url": redact_url(request.url),
            "host": parsed.netloc,
            "path": parsed.path,
            "query": redact_query(parse_qsl(parsed.query, keep_blank_values=True)),
            "frame_url": redact_url(frame_url) if frame_url else None,
            "request_headers": redact_headers(headers),
        }
        if post_data:
            entry["request_bytes"] = len(post_data)
            entry["request_body_file"] = self._write_body(f"{seq:05d}.request.txt", post_data)
            parsed_body = parse_json_bytes(post_data)
            if parsed_body is not None:
                entry["request_shape"] = summarize_shape(parsed_body)
                operation = graphql_operation(parsed_body)
                if operation:
                    entry["graphql_operation"] = operation
                    entry["graphql_variables"] = parsed_body.get("variables")
                    entry["endpoint"] = f"{entry['endpoint']} #{operation}"
        return entry

    def _on_finished(self, request: Any) -> None:  # noqa: ANN401
        try:
            if request.resource_type not in self.resource_types:
                return
            seq = self._next_seq()
            entry = self._base_entry(request, seq)
            response = request.response()
            if response is not None:
                headers = response.all_headers()
                content_type = (headers.get("content-type") or "").lower()
                entry.update(
                    {
                        "status": response.status,
                        "content_type": content_type,
                        "response_headers": redact_headers(headers),
                    },
                )
                if TEXT_CONTENT_RE.search(content_type) or not content_type:
                    body = response.body()
                    entry["response_bytes"] = len(body)
                    if len(body) <= self.max_body_bytes:
                        entry["response_body_file"] = self._write_body(
                            f"{seq:05d}.response.{_body_extension(content_type)}",
                            body,
                        )
                    parsed_body = parse_json_bytes(body)
                    if parsed_body is not None:
                        entry["response_shape"] = summarize_shape(parsed_body)
            timing = request.timing
            if timing and timing.get("responseEnd", -1) >= 0:
                entry["duration_ms"] = round(timing["responseEnd"], 1)
            self.calls.append(entry)
            self._append(entry)
        except Exception as exc:  # noqa: BLE001 - capture must never break the page
            self._append({"type": "capture_error", "error": str(exc), "at": _now()})

    def _on_failed(self, request: Any) -> None:  # noqa: ANN401
        try:
            if request.resource_type not in self.resource_types:
                return
            entry = self._base_entry(request, self._next_seq())
            entry["failure"] = request.failure
            self.calls.append(entry)
            self._append(entry)
        except Exception as exc:  # noqa: BLE001
            self._append({"type": "capture_error", "error": str(exc), "at": _now()})

    def _calls_since(self, since_mark: str | None) -> list[dict[str, Any]]:
        if not since_mark:
            return list(self.calls)
        matches = [m for m in self.marks if m["label"] == since_mark]
        if not matches:
            msg = f"No mark named {since_mark!r}"
            raise LookupError(msg)
        after = matches[-1]["after_seq"]
        return [c for c in self.calls if c["seq"] > after]

    def catalog(
        self,
        *,
        since_mark: str | None = None,
        host_pattern: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        calls = self._calls_since(since_mark)
        if host_pattern:
            host_re = re.compile(host_pattern, re.I)
            calls = [c for c in calls if host_re.search(c["host"])]
        endpoints = build_catalog(calls, self.marks)
        result = {
            "generated_at": _now(),
            "since_mark": since_mark,
            "host_pattern": host_pattern,
            "call_count": len(calls),
            "endpoint_count": len(endpoints),
            "marks": self.marks,
            "endpoints": endpoints,
        }
        if write:
            path = self.out_dir / "catalog.json"
            path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
            result["path"] = str(path)
        return result

    def show(self, seq: int, *, preview_chars: int = 2000) -> dict[str, Any]:
        call = next((c for c in self.calls if c["seq"] == seq), None)
        if call is None:
            msg = f"No captured call with seq {seq}"
            raise LookupError(msg)
        result = dict(call)
        body_file = call.get("response_body_file")
        if body_file and preview_chars > 0:
            text = Path(body_file).read_text(encoding="utf-8", errors="replace")
            result["response_preview"] = text[:preview_chars]
        request_file = call.get("request_body_file")
        if request_file and preview_chars > 0:
            text = Path(request_file).read_text(encoding="utf-8", errors="replace")
            result["request_preview"] = text[:preview_chars]
        return result

    def replay(
        self,
        api_request: Any,  # noqa: ANN401 - playwright APIRequestContext
        seq: int,
        *,
        query: dict[str, Any] | None = None,
        json_patch: dict[str, Any] | None = None,
        body: str | None = None,
        url: str | None = None,
        method: str | None = None,
        preview_chars: int = 1000,
        timeout_ms: int = 120_000,
    ) -> dict[str, Any]:
        """Re-issue a captured call through the browser context's cookies and original headers.

        ``json_patch`` keys are dotted paths into a JSON request body.
        """
        raw = self._raw.get(seq)
        if raw is None:
            msg = f"No captured request with seq {seq} (raw requests are kept for this daemon session only)"
            raise LookupError(msg)
        target_url = url or raw["url"]
        if query:
            target_url = apply_query_overrides(target_url, query)
        headers = {
            k: v for k, v in raw["headers"].items() if not k.startswith(":") and k.lower() not in REPLAY_DROP_HEADERS
        }
        data: bytes | str | None = raw["post_data"]
        if body is not None:
            data = body
        elif json_patch:
            parsed_body = parse_json_bytes(data or b"{}")
            if not isinstance(parsed_body, dict):
                msg = f"Request body of seq {seq} is not a JSON object; pass body instead"
                raise ValueError(msg)
            for path, value in json_patch.items():
                _set_dotted(parsed_body, path, value)
            data = json.dumps(parsed_body)

        started = datetime.now(UTC)
        response = api_request.fetch(
            target_url,
            method=method or raw["method"],
            headers=headers,
            data=data,
            timeout=timeout_ms,
            fail_on_status_code=False,
        )
        elapsed_ms = round((datetime.now(UTC) - started).total_seconds() * 1000, 1)
        response_body = response.body()
        content_type = (response.headers.get("content-type") or "").lower()
        replay_seq = self._next_seq()
        entry: dict[str, Any] = {
            "type": "replay",
            "seq": replay_seq,
            "replay_of": seq,
            "at": _now(),
            "method": method or raw["method"],
            "endpoint": endpoint_key(method or raw["method"], target_url),
            "url": redact_url(target_url),
            "query_overrides": query,
            "json_patch": json_patch,
            "status": response.status,
            "content_type": content_type,
            "duration_ms": elapsed_ms,
            "response_bytes": len(response_body),
            "response_body_file": self._write_body(
                f"{replay_seq:05d}.replay-of-{seq:05d}.response.{_body_extension(content_type)}",
                response_body,
            ),
        }
        parsed_response = parse_json_bytes(response_body)
        if parsed_response is not None:
            entry["response_shape"] = summarize_shape(parsed_response)
        self._append(entry)
        result = dict(entry)
        if preview_chars > 0:
            result["response_preview"] = response_body[:preview_chars].decode("utf-8", errors="replace")
        return result


def build_catalog(calls: list[dict[str, Any]], marks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Group captured calls by endpoint (method + host + templated path)."""
    marks = marks or []
    grouped: dict[str, dict[str, Any]] = {}
    for call in calls:
        key = call["endpoint"]
        group = grouped.get(key)
        if group is None:
            group = {
                "endpoint": key,
                "count": 0,
                "statuses": {},
                "content_types": set(),
                "resource_types": set(),
                "frames": set(),
                "query_params": {},
                "response_bytes": [],
                "durations_ms": [],
                "after_marks": set(),
                "seqs": [],
                "response_shape": None,
                "request_shape": None,
            }
            grouped[key] = group
        group["count"] += 1
        status = str(call.get("status", call.get("failure") or "?"))
        group["statuses"][status] = group["statuses"].get(status, 0) + 1
        if call.get("content_type"):
            group["content_types"].add(call["content_type"].split(";")[0])
        group["resource_types"].add(call.get("resource_type"))
        if call.get("frame_url"):
            frame = urlparse(call["frame_url"])
            group["frames"].add(f"{frame.netloc}{frame.path}")
        for name, value in call.get("query") or []:
            samples = group["query_params"].setdefault(name, [])
            if value not in samples and len(samples) < 5:
                samples.append(value)
        if call.get("response_bytes") is not None:
            group["response_bytes"].append(call["response_bytes"])
        if call.get("duration_ms") is not None:
            group["durations_ms"].append(call["duration_ms"])
        preceding = [m["label"] for m in marks if m["after_seq"] < call["seq"]]
        if preceding:
            group["after_marks"].add(preceding[-1])
        group["seqs"].append(call["seq"])
        if group["response_shape"] is None and call.get("response_shape") is not None:
            group["response_shape"] = call["response_shape"]
        if group["request_shape"] is None and call.get("request_shape") is not None:
            group["request_shape"] = call["request_shape"]
        if call.get("graphql_variables") is not None:
            variants = group.setdefault("graphql_variables", [])
            if call["graphql_variables"] not in variants and len(variants) < 5:
                variants.append(call["graphql_variables"])

    endpoints = []
    for group in grouped.values():
        sizes = group.pop("response_bytes")
        durations = group.pop("durations_ms")
        group["response_bytes"] = {"min": min(sizes), "max": max(sizes)} if sizes else None
        group["duration_ms"] = {"min": min(durations), "max": max(durations)} if durations else None
        for name in ("content_types", "resource_types", "frames", "after_marks"):
            group[name] = sorted(v for v in group[name] if v)
        group["seqs"] = group["seqs"][:25]
        endpoints.append(group)
    endpoints.sort(key=lambda g: (-(g["response_bytes"] or {}).get("max", 0), g["endpoint"]))
    return endpoints
