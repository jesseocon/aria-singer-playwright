from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from singer_playwright.workshop.downloads import DownloadRecorder, sniff_format


class FakeDownload:
    def __init__(self, body: bytes, suggested: str, *, failure: str | None = None) -> None:
        self._body = body
        self.suggested_filename = suggested
        self.url = "https://secure-backend.example.com/Reserved.ReportViewerWebControl.axd?OpType=Export"
        self._failure = failure

    def failure(self) -> str | None:
        return self._failure

    def save_as(self, path: str) -> None:
        Path(path).write_bytes(self._body)


class FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, list[Any]] = {}
        self.waits = 0

    def on(self, event: str, handler: Any) -> None:  # noqa: ANN401
        # Playwright's sync API sets an attribute on handlers, which builtins reject.
        handler.__dict__  # noqa: B018
        self.handlers.setdefault(event, []).append(handler)

    def emit(self, event: str, payload: Any) -> None:  # noqa: ANN401
        for handler in self.handlers.get(event, []):
            handler(payload)

    def wait_for_timeout(self, _ms: int) -> None:
        self.waits += 1


class FakeContext:
    def __init__(self) -> None:
        self.pages = [FakePage()]
        self.handlers: dict[str, list[Any]] = {}

    def on(self, event: str, handler: Any) -> None:  # noqa: ANN401
        self.handlers.setdefault(event, []).append(handler)

    def open_popup(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        for handler in self.handlers.get("page", []):
            handler(page)
        return page


def test_saves_csv_download_with_preview_and_log(tmp_path: Path) -> None:
    context = FakeContext()
    recorder = DownloadRecorder(tmp_path / "downloads")
    recorder.attach(context)

    context.pages[0].emit("download", FakeDownload(b"\xef\xbb\xbfHotel,OT Hours\nAloft,11.27\n", "report.csv"))
    saved = recorder.wait_for_next(context.pages[0], timeout_ms=1000, name="ot-usage 2026-09-01")

    assert saved["format"] == "text"
    assert saved["preview"].startswith("Hotel,OT Hours")
    assert Path(saved["path"]).name == "001-ot-usage_2026-09-01.csv"
    logged = [json.loads(line) for line in (tmp_path / "downloads" / "downloads.jsonl").read_text().splitlines()]
    assert logged[0]["suggested_filename"] == "report.csv"


def test_captures_downloads_from_popup_pages(tmp_path: Path) -> None:
    context = FakeContext()
    recorder = DownloadRecorder(tmp_path / "downloads")
    recorder.attach(context)

    popup = context.open_popup()
    popup.emit("download", FakeDownload(b"PK\x03\x04rest-of-xlsx", "report.xlsx"))

    listing = recorder.list()
    assert listing["count"] == 1
    assert listing["downloads"][0]["format"] == "zip"
    assert "preview" not in listing["downloads"][0]


def test_failed_download_is_recorded_without_file(tmp_path: Path) -> None:
    context = FakeContext()
    recorder = DownloadRecorder(tmp_path / "downloads")
    recorder.attach(context)

    context.pages[0].emit("download", FakeDownload(b"", "report.csv", failure="canceled"))
    saved = recorder.flush()[0]

    assert saved["failure"] == "canceled"
    assert not Path(saved["path"]).exists()


def test_wait_for_next_times_out(tmp_path: Path) -> None:
    context = FakeContext()
    recorder = DownloadRecorder(tmp_path / "downloads")
    recorder.attach(context)

    with pytest.raises(TimeoutError):
        recorder.wait_for_next(context.pages[0], timeout_ms=0)


def test_sniff_format() -> None:
    assert sniff_format(b"PK\x03\x04abc") == "zip"
    assert sniff_format(b"\xd0\xcf\x11\xe0abc") == "ole"
    assert sniff_format(b"a,b\n1,2\n") == "text"
    assert sniff_format(b"\x89PNG\x00\x00") == "binary"
