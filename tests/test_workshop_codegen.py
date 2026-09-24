"""Tests for recipe codegen."""

from __future__ import annotations

from pathlib import Path

from singer_playwright.workshop.codegen import compile_recipe_file
from singer_playwright.workshop.schema import infer_schema_from_records

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STRATEGY_RECIPE = FIXTURES / "strategy-snapshot.recipe.json"


def test_infer_schema_from_records() -> None:
    schema = infer_schema_from_records(
        [
            {"date": "2026-01-01", "revenue": "100", "rooms": 10},
            {"date": "2026-01-02", "revenue": "200", "rooms": 12},
        ],
    )
    assert "date" in schema["properties"]
    assert "revenue" in schema["properties"]
    assert schema["additionalProperties"] is True


def test_compile_strategy_snapshot_recipe(tmp_path: Path) -> None:
    manifest = compile_recipe_file(
        STRATEGY_RECIPE,
        output_dir=tmp_path,
    )
    assert manifest["stream"] == "strategy-snapshot"
    assert any("strategy_snapshot_stream.py" in path for path in manifest["files"])
    stream_file = tmp_path / "generated" / "strategy_snapshot_stream.py"
    assert stream_file.is_file()
    content = stream_file.read_text(encoding="utf-8")
    assert "StrategySnapshotStream" in content
    assert "navigate_strategy_snapshot" in content
