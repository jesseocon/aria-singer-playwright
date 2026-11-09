"""fill --value-env: sign-in values typed from the daemon's environment, never recorded."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from singer_playwright.workshop.network import NetworkRecorder
from singer_playwright.workshop.recipe import fill_value
from test_workshop_network import FakeRequest

PASSWORD = "p@ss w0rd&\"x"


def test_fill_value_reads_the_named_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAP_PASSWORD", PASSWORD)
    assert fill_value({"value_env": "TAP_PASSWORD"}) == PASSWORD
    assert fill_value({"value": "plain"}) == "plain"
    monkeypatch.delenv("TAP_PASSWORD")
    with pytest.raises(ValueError, match="TAP_PASSWORD is not set"):
        fill_value({"value_env": "TAP_PASSWORD"})


def test_saved_request_bodies_never_hold_a_sealed_value(tmp_path: Path) -> None:
    recorder = NetworkRecorder(tmp_path / "network")
    recorder.add_secret(PASSWORD)
    from urllib.parse import urlencode

    form = urlencode({"user": "ada", "password": PASSWORD}).encode()
    recorder._on_finished(FakeRequest("https://vendor.example/login", method="POST", post=form))
    recorder._on_finished(
        FakeRequest("https://vendor.example/api/login", method="POST", post=json.dumps({"password": PASSWORD}).encode()),
    )
    saved = b"".join(p.read_bytes() for p in (tmp_path / "network" / "bodies").iterdir())
    saved += (tmp_path / "network" / "calls.jsonl").read_bytes()
    assert PASSWORD.encode() not in saved
    assert urlencode({"p": PASSWORD}).split("=", 1)[1].encode() not in saved
    assert json.dumps(PASSWORD)[1:-1].encode() not in saved
    assert b"[sealed]" in saved and b"user=ada" in saved


def test_the_cli_sends_the_name_not_the_value(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import argparse

    from singer_playwright.workshop import cli

    sent: dict = {}
    monkeypatch.setenv("TAP_PASSWORD", PASSWORD)
    monkeypatch.setattr(cli.workshop_client, "act", lambda action, **params: sent.update(params) or {"ok": True, "params": params})
    parser = argparse.ArgumentParser()
    cli.add_workshop_parser(parser.add_subparsers(dest="command"))
    args = parser.parse_args(["workshop", "act", "fill", "--selector", "#pw", "--value-env", "TAP_PASSWORD"])
    cli.handle_workshop(args)
    assert sent == {"selector": "#pw", "value_env": "TAP_PASSWORD"}
    assert PASSWORD not in capsys.readouterr().out
