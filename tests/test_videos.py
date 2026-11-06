import json
import logging

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.progress import MARKER


def _visit(runtime: BrowserRuntime) -> None:
    runtime.page.route("https://video.test/**", lambda route: route.fulfill(status=200, content_type="text/html", body="<h1>hello</h1>"))
    runtime.page.goto("https://video.test/")
    runtime.page.wait_for_timeout(300)


def test_a_run_that_asks_for_video_gets_one_webm_and_a_notice(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setenv("ARIA_SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("ARIA_RECORD_VIDEO", "1")
    logger = logging.getLogger("test-videos")
    with caplog.at_level(logging.INFO, logger="test-videos"):
        with BrowserRuntime(BrowserConfig(storage_state_path=None), logger) as runtime:
            _visit(runtime)
    files = sorted(p.name for p in tmp_path.iterdir())
    assert len(files) == 1 and files[0].endswith("-browser.webm"), files
    assert (tmp_path / files[0]).stat().st_size > 0
    events = [json.loads(r.getMessage().removeprefix(MARKER)) for r in caplog.records if r.getMessage().startswith(MARKER)]
    assert [(e["kind"], e["code"], e["video"]) for e in events] == [("notice", "video", files[0])]


def test_no_video_unless_the_run_asks(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ARIA_SCREENSHOT_DIR", str(tmp_path))
    monkeypatch.delenv("ARIA_RECORD_VIDEO", raising=False)
    with BrowserRuntime(BrowserConfig(storage_state_path=None)) as runtime:
        _visit(runtime)
    assert list(tmp_path.iterdir()) == []


def test_no_video_outside_a_run(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ARIA_SCREENSHOT_DIR", raising=False)
    monkeypatch.setenv("ARIA_RECORD_VIDEO", "1")
    with BrowserRuntime(BrowserConfig(storage_state_path=None)) as runtime:
        _visit(runtime)
