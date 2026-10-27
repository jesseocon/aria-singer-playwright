"""wait_for_code asks the run's broker through files and returns the code it is handed."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime

import pytest

from singer_playwright import codes


def _broker(folder, reply: dict) -> threading.Thread:
    def answer() -> None:
        for _ in range(200):
            requests = list(folder.glob("*.request"))
            if requests:
                ask = json.loads(requests[0].read_text())
                assert ask["address"] == "wyndham-okta@codes.example.com"
                requests[0].with_suffix(".code").write_text(json.dumps(reply))
                return
            threading.Event().wait(0.01)

    thread = threading.Thread(target=answer)
    thread.start()
    return thread


def test_the_code_handed_over_by_the_broker_is_returned(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(codes.DIR_ENV, str(tmp_path))
    thread = _broker(tmp_path, {"code": "482915"})
    code = codes.wait_for_code("wyndham-okta@codes.example.com", after=datetime.now(UTC), poll_s=0.01)
    thread.join()
    assert code == "482915"
    assert list(tmp_path.iterdir()) == []  # request and answer are cleaned up


def test_a_refused_inbox_and_a_timeout_raise(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv(codes.DIR_ENV, str(tmp_path))
    thread = _broker(tmp_path, {"error": "this run's login does not use that code inbox"})
    with pytest.raises(codes.CodeUnavailable, match="does not use"):
        codes.wait_for_code("wyndham-okta@codes.example.com", after=datetime.now(UTC), poll_s=0.01)
    thread.join()
    with pytest.raises(codes.CodeUnavailable, match="within 0s"):
        codes.wait_for_code("wyndham-okta@codes.example.com", after=datetime.now(UTC), timeout_s=0.05, poll_s=0.01)


def test_outside_a_run_there_is_no_inbox(monkeypatch) -> None:
    monkeypatch.delenv(codes.DIR_ENV, raising=False)
    with pytest.raises(codes.CodeUnavailable, match="no code inbox"):
        codes.wait_for_code("x@codes.example.com", after=datetime.now(UTC))
