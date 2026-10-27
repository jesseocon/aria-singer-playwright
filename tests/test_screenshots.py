"""Screenshots land in the run's folder, are reported by name, and never raise."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from singer_playwright import progress, screenshots
from singer_playwright.stream import PlaywrightStream


class FakePage:
    url = "https://product.costar.com/app/str/dashboard"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    def is_closed(self) -> bool:
        return False

    def screenshot(self, *, path: str, type: str, quality: int, timeout: int) -> None:  # noqa: A002
        assert type == "jpeg" and path.endswith(".jpg.part")
        if self.fail:
            raise TimeoutError("page is gone")
        Path(path).write_bytes(b"\xff\xd8jpeg")


def _events(caplog) -> list[dict]:
    return [json.loads(r.getMessage().split(progress.MARKER, 1)[1]) for r in caplog.records if progress.MARKER in r.getMessage()]


def test_a_screenshot_is_saved_complete_and_reported(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv(screenshots.DIR_ENV, str(tmp_path))
    caplog.set_level(logging.INFO)
    name = screenshots.screenshot(FakePage(), "SessionExpired on SegDayOfWeekTable", logging.getLogger("t"), stream="str_series")
    assert name and name.endswith("-sessionexpired-on-segdayofweektable.jpg")
    assert [p.name for p in tmp_path.iterdir()] == [name]
    event = _events(caplog)[0]
    assert (event["kind"], event["code"], event["screenshot"], event["stream"]) == ("notice", "screenshot", name, "str_series")
    assert "dashboard" in event["message"]


def test_without_a_run_folder_or_on_failure_nothing_is_saved_and_nothing_raises(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.delenv(screenshots.DIR_ENV, raising=False)
    assert screenshots.screenshot(FakePage(), "x", logging.getLogger("t")) is None
    monkeypatch.setenv(screenshots.DIR_ENV, str(tmp_path))
    assert screenshots.screenshot(FakePage(fail=True), "x", logging.getLogger("t")) is None
    assert screenshots.screenshot(None, "x", logging.getLogger("t")) is None
    assert list(tmp_path.iterdir()) == [] or all(p.suffix == ".part" for p in tmp_path.iterdir())
    assert _events(caplog) == []


class _Runtime:
    page = FakePage()


class _Tap:
    _browser_runtime = _Runtime()

    def rate_limit(self) -> None:
        return None


class _FailingStream(PlaywrightStream):
    name = "str_series"
    schema = {"type": "object", "properties": {}}  # noqa: RUF012

    def __init__(self) -> None:
        pass

    @property
    def logger(self) -> logging.Logger:  # type: ignore[override]
        return logging.getLogger("tap-test")

    @property
    def playwright_tap(self) -> _Tap:  # type: ignore[override]
        return _Tap()

    @property
    def page(self) -> FakePage:  # type: ignore[override]
        return _Runtime.page

    def extract_records(self, page, context):  # noqa: ANN001, ANN201
        yield {"id": 1}
        raise RuntimeError("SessionExpired")


def test_a_failing_stream_keeps_a_screenshot_before_reporting_the_error(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv(screenshots.DIR_ENV, str(tmp_path))
    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError):
        list(_FailingStream().get_records(None))
    kinds = [(e["kind"], e.get("code")) for e in _events(caplog)]
    assert kinds == [("stream.started", None), ("notice", "screenshot"), ("error", None)]
    assert len(list(tmp_path.glob("*.jpg"))) == 1
