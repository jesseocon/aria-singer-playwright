"""Human pacing: uneven typing, curved mouse travel, uneven waits; plain when turned off."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from singer_playwright import human
from singer_playwright.browser import BrowserConfig, BrowserRuntime


def test_off_means_plain_and_instant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(human.ENV, "0")
    locator = MagicMock()
    human.type_text(locator, "secret")
    locator.fill.assert_called_once_with("secret")
    human.click(locator)
    locator.click.assert_called_once_with()
    assert human.pause() == 0.0
    assert human.Pacer(5).wait() == 0.0


def test_pacer_waits_unevenly_and_takes_breaks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(human.ENV, raising=False)
    waited: list[float] = []
    monkeypatch.setattr(human, "_wait", lambda seconds, _page: waited.append(seconds))
    pacer = human.Pacer(2.0, break_every=5, break_median=20.0)
    for _ in range(10):
        pacer.wait()
    assert len(set(round(w, 3) for w in waited)) > 5  # uneven
    assert waited[4] > 5 and waited[9] > 5  # every fifth is a break
    assert max(waited) <= 80


def test_typing_and_clicking_in_a_real_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(human.ENV, raising=False)
    monkeypatch.setattr(human, "_jitter", lambda median, spread=0.45: 0.01)  # fast test
    with BrowserRuntime(BrowserConfig()) as runtime:
        page = runtime.page
        page.route("https://human.test/**", lambda r: r.fulfill(status=200, content_type="text/html", body=(
            "<input id=u><button id=b onclick=\"window.clicked=[event.offsetX,event.offsetY,event.isTrusted]\">Go</button>"
            "<script>window.keys=0;document.getElementById('u').addEventListener('keydown',()=>window.keys++)</script>")))
        page.goto("https://human.test/")
        human.type_text(page.locator("#u"), "ada")
        human.click(page.locator("#b"))
        assert page.input_value("#u") == "ada"
        assert page.evaluate("window.keys") == 3  # one key at a time
        assert page.evaluate("window.clicked[2]") is True
