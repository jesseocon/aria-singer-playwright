"""Tests for workshop brief loading and evaluation."""

from __future__ import annotations

from pathlib import Path

from singer_playwright.workshop.brief import evaluate_success, load_brief

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_strategy_snapshot_brief() -> None:
    brief = load_brief(REPO_ROOT / "briefs/strategy-snapshot.yaml")
    assert brief.tap == "tap-lighthouse"
    assert brief.stream == "strategy-snapshot"
    assert brief.success.min_records == 30
    assert "202158" in brief.render_url()


def test_evaluate_success_passes() -> None:
    brief = load_brief(REPO_ROOT / "briefs/strategy-snapshot.yaml")
    result = evaluate_success(
        brief,
        records=[{"date": "2026-01-01", "revenue": "100"}] * 30,
        login_page=False,
    )
    assert result["passed"] is True


def test_evaluate_success_fails_on_login_page() -> None:
    brief = load_brief(REPO_ROOT / "briefs/strategy-snapshot.yaml")
    result = evaluate_success(
        brief,
        records=[{"date": "2026-01-01"}] * 30,
        login_page=True,
    )
    assert result["passed"] is False
