"""Tests for workshop recipe loading and step execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from singer_playwright.workshop.recipe import execute_step, load_recipe, run_recipe_steps

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STRATEGY_RECIPE = FIXTURES / "strategy-snapshot.recipe.json"


def test_load_strategy_snapshot_recipe() -> None:
    recipe = load_recipe(STRATEGY_RECIPE)
    assert recipe.version == 1
    assert recipe.brief["stream"] == "strategy-snapshot"
    assert len(recipe.steps) >= 3
    assert recipe.extract.selector == "table.analytics.day-by-day"


def test_execute_goto_step() -> None:
    page = MagicMock()
    page.url = "https://example.com"
    result = execute_step(page, {"type": "goto", "url": "https://example.com"})
    page.goto.assert_called_once_with("https://example.com", wait_until="domcontentloaded")
    assert result["ok"] is True


@patch("singer_playwright.workshop.recipe._find_frame")
def test_run_recipe_steps(mock_find_frame: MagicMock) -> None:
    page = MagicMock()
    frame = MagicMock()
    frame.url = "https://spider.kriyarevgen.com/dashboards/day-by-day"
    mock_find_frame.return_value = frame

    recipe = load_recipe(STRATEGY_RECIPE)
    with patch("singer_playwright.workshop.recipe.execute_step") as mock_execute:
        mock_execute.side_effect = lambda _page, step: {"type": step["type"], "ok": True}
        results = run_recipe_steps(page, recipe.steps[:2])
    assert len(results) == 2
