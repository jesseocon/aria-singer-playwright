"""Streams report progress lines aria-runner can read."""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from singer_playwright import progress
from singer_playwright.stream import PlaywrightStream


def _events(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    out = []
    for record in caplog.records:
        text = record.getMessage()
        if progress.MARKER in text:
            out.append(json.loads(text.split(progress.MARKER, 1)[1]))
    return out


class _Tap:
    def rate_limit(self) -> None:
        return None


class _Stream(PlaywrightStream):
    name = "journal_lines"
    schema = {"type": "object", "properties": {}}  # noqa: RUF012

    def __init__(self, rows: list[dict] | Exception, *, skip: str | None = None) -> None:
        self._rows = rows
        self._skip = skip

    @property
    def logger(self) -> logging.Logger:  # type: ignore[override]
        return logging.getLogger("tap-test")

    @property
    def playwright_tap(self) -> _Tap:  # type: ignore[override]
        return _Tap()

    @property
    def page(self) -> None:  # type: ignore[override]
        return None

    def extract_records(self, page, context):  # noqa: ANN001, ANN201
        if self._skip:
            self.skip(self._skip, code="not_entitled")
            return
        if isinstance(self._rows, Exception):
            yield {"id": 1}
            raise self._rows
        self.progress(1, 2, "months")
        yield from self._rows


def test_a_stream_reports_start_progress_and_finish_with_rows(caplog) -> None:
    caplog.set_level(logging.INFO)
    rows = list(_Stream([{"id": 1}, {"id": 2}]).get_records(None))
    assert len(rows) == 2
    assert [(e["kind"], e.get("records")) for e in _events(caplog)] == [
        ("stream.started", None),
        ("stream.progress", None),
        ("stream.finished", 2),
    ]
    assert all(e["v"] == 1 and e["stream"] == "journal_lines" for e in _events(caplog))


def test_a_skipped_stream_does_not_also_finish(caplog) -> None:
    caplog.set_level(logging.INFO)
    assert list(_Stream([], skip="not entitled").get_records(None)) == []
    assert [e["kind"] for e in _events(caplog)] == ["stream.started", "stream.skipped"]
    assert _events(caplog)[1]["reason"] == "not entitled"


def test_a_failing_stream_reports_the_error_and_still_raises(caplog) -> None:
    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError):
        list(_Stream(RuntimeError("grid paging broke")).get_records(None))
    kinds = [e["kind"] for e in _events(caplog)]
    assert kinds == ["stream.started", "error"]
    assert "grid paging broke" in _events(caplog)[1]["message"]


def test_bad_events_are_refused_but_report_never_raises(caplog) -> None:
    with pytest.raises(ValueError, match="needs reason"):
        progress.line("stream.skipped", stream="x")
    progress.report(logging.getLogger("tap-test"), "stream.skipped", stream="x")
