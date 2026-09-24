"""Workshop page_scripts.js resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from singer_playwright.workshop.observe import (
    clear_workshop_scripts_cache,
    load_workshop_scripts_source,
    resolve_workshop_scripts_path,
)


def test_resolve_lighthouse_workshop_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    lighthouse_root = Path(__file__).resolve().parents[2] / "aria-lighthouse"
    if not (lighthouse_root / "workshop" / "page_scripts.js").is_file():
        pytest.skip("aria-lighthouse sibling checkout not present")

    monkeypatch.chdir(lighthouse_root)
    monkeypatch.delenv("SINGER_PLAYWRIGHT_WORKSHOP_SCRIPTS", raising=False)
    monkeypatch.setenv("MELTANO_PROJECT_ROOT", str(lighthouse_root))
    clear_workshop_scripts_cache()

    path = resolve_workshop_scripts_path()
    assert path is not None
    assert path.name == "page_scripts.js"
    source = load_workshop_scripts_source()
    assert "findTableCandidatesScript" in source
    assert "table.analytics.day-by-day" in source


def test_minimal_fallback_when_no_project_scripts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SINGER_PLAYWRIGHT_WORKSHOP_SCRIPTS", raising=False)
    monkeypatch.delenv("MELTANO_PROJECT_ROOT", raising=False)
    clear_workshop_scripts_cache()

    assert resolve_workshop_scripts_path() is None
    source = load_workshop_scripts_source()
    assert "collectPageInfoScript" in source
