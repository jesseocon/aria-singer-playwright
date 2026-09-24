"""Compact page observations for agent-driven scraper iteration."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

WORKSHOP_SCRIPTS_ENV = "SINGER_PLAYWRIGHT_WORKSHOP_SCRIPTS"
WORKSHOP_SCRIPTS_RELATIVE = Path("workshop") / "page_scripts.js"

_MINIMAL_WORKSHOP_SCRIPTS = """
function normalizeText(value) {
  return (value ?? "").replace(/\\s+/g, " ").trim();
}
function collectPageInfoScript(pageLabel) {
  const bodyText = normalizeText(document.body?.textContent ?? "");
  return {
    label: pageLabel,
    url: location.href,
    title: document.title,
    tabs: [],
    subNav: [],
    links: [],
    buttons: [],
    iframeCount: document.querySelectorAll("iframe").length,
    loginSignals: {
      hasEmailInput: !!document.querySelector('input[type="email"]'),
      hasPasswordInput: !!document.querySelector('input[type="password"]'),
      loginMarkers: [],
      urlLooksLikeLogin: /login|signin|sign-in/i.test(location.href),
    },
    bodyPreview: bodyText.slice(0, 1500),
  };
}
function getInteractiveControlsScript() { return []; }
function findTableCandidatesScript() { return []; }
function extractTableScript(selector) {
  const table = selector ? document.querySelector(selector) : null;
  if (!table) {
    return { headers: [], rows: [], error: selector ? "Selector not found: " + selector : "No table found" };
  }
  const headerCells = Array.from(table.querySelectorAll("thead th, [role='columnheader']"));
  const headers = headerCells.map((cell, index) => {
    const text = normalizeText(cell.textContent).replace(/\\s+/g, "_").toLowerCase();
    return text || "column_" + index;
  });
  const bodyRows = Array.from(table.querySelectorAll("tbody tr, [role='row']")).filter((row) =>
    row.querySelector("td, [role='gridcell'], [role='cell']"),
  );
  const rows = bodyRows.slice(0, 500).map((row) => {
    const cells = Array.from(row.querySelectorAll("td, [role='gridcell'], [role='cell']"));
    const record = {};
    cells.forEach((cell, index) => {
      const key = headers[index] || "column_" + index;
      record[key] = normalizeText(cell.textContent);
    });
    return record;
  });
  return { headers, rows, error: null, rowCount: rows.length };
}
function analyzePageScript() {
  return {
    url: location.href,
    title: document.title,
    loading: { loading: false, reason: null },
    tables: [],
    bodyPreview: normalizeText(document.body?.textContent ?? "").slice(0, 1200),
  };
}
"""


def _scripts_path_under(root: Path) -> Path | None:
    path = root / WORKSHOP_SCRIPTS_RELATIVE
    if path.is_file():
        return path.resolve()
    return None


def resolve_workshop_scripts_path() -> Path | None:
    """Locate project-specific workshop JS (e.g. Lighthouse ``workshop/page_scripts.js``)."""
    env_path = os.environ.get(WORKSHOP_SCRIPTS_ENV)
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_file():
            return path.resolve()

    meltano_root = os.environ.get("MELTANO_PROJECT_ROOT")
    if meltano_root:
        found = _scripts_path_under(Path(meltano_root).expanduser())
        if found:
            return found

    try:
        from singer_playwright.workshop.runs import load_session_file

        session = load_session_file()
        session_root = session.get("project_root")
        if session_root:
            found = _scripts_path_under(Path(session_root))
            if found:
                return found
    except FileNotFoundError:
        pass

    found = _scripts_path_under(Path.cwd())
    if found:
        return found

    return None


@lru_cache(maxsize=1)
def load_workshop_scripts_source() -> str:
    path = resolve_workshop_scripts_path()
    if path is not None:
        return path.read_text(encoding="utf-8")
    return _MINIMAL_WORKSHOP_SCRIPTS


def clear_workshop_scripts_cache() -> None:
    load_workshop_scripts_source.cache_clear()


def _evaluate_script(function_name: str, target: Page | Frame, *args: object) -> Any:
    scripts_source = load_workshop_scripts_source()
    arg_literals = ", ".join(repr(arg) for arg in args)
    expression = f"""(() => {{
        {scripts_source}
        return {function_name}({arg_literals});
    }})()"""
    return target.evaluate(expression)


def list_frames(page: Page) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    for index, frame in enumerate(page.frames):
        frames.append(
            {
                "index": index,
                "name": frame.name,
                "url": frame.url,
                "is_main": frame == page.main_frame,
            },
        )
    return frames


def find_frame_by_pattern(page: Page, url_pattern: str) -> Frame | None:
    pattern = re.compile(url_pattern, re.I)
    for frame in page.frames:
        if pattern.search(frame.url):
            return frame
    return None


def resolve_target(page: Page, *, frame_index: int | None = None, frame_url_pattern: str | None = None) -> Page | Frame:
    if frame_index is not None:
        frames = page.frames
        if frame_index < 0 or frame_index >= len(frames):
            msg = f"frame_index {frame_index} out of range (0..{len(frames) - 1})"
            raise IndexError(msg)
        return frames[frame_index]

    if frame_url_pattern:
        frame = find_frame_by_pattern(page, frame_url_pattern)
        if frame is None:
            msg = f"No frame matched pattern: {frame_url_pattern}"
            raise LookupError(msg)
        return frame

    return page


def observe_page(
    page: Page,
    *,
    frame_index: int | None = None,
    frame_url_pattern: str | None = None,
    xhr_log: list[dict[str, Any]] | None = None,
    label: str = "current",
) -> dict[str, Any]:
    """Return a compact page model suitable for LLM context."""
    clear_workshop_scripts_cache()
    target = resolve_target(
        page,
        frame_index=frame_index,
        frame_url_pattern=frame_url_pattern,
    )

    scripts_path = resolve_workshop_scripts_path()
    page_info = _evaluate_script("collectPageInfoScript", target, label)
    controls = _evaluate_script("getInteractiveControlsScript", target)
    tables = _evaluate_script("findTableCandidatesScript", target)
    analysis = _evaluate_script("analyzePageScript", target)

    recent_xhr = list(xhr_log or [])[-15:]

    return {
        "label": label,
        "target": {
            "frame_index": frame_index,
            "frame_url_pattern": frame_url_pattern,
            "url": page_info.get("url"),
            "title": page_info.get("title"),
        },
        "frames": list_frames(page),
        "page": page_info,
        "controls": controls,
        "tables": tables,
        "analysis": analysis,
        "xhr": recent_xhr,
        "login_page": _looks_like_login(page_info),
        "workshop_scripts_path": str(scripts_path) if scripts_path else None,
    }


def extract_table(
    page: Page,
    *,
    selector: str | None = None,
    frame_index: int | None = None,
    frame_url_pattern: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    clear_workshop_scripts_cache()
    target = resolve_target(
        page,
        frame_index=frame_index,
        frame_url_pattern=frame_url_pattern,
    )
    result = _evaluate_script("extractTableScript", target, selector or "")
    rows = list(result.get("rows") or [])[:limit]
    return {
        "headers": result.get("headers") or [],
        "rows": rows,
        "row_count": len(rows),
        "error": result.get("error"),
    }


def _looks_like_login(page_info: dict[str, Any]) -> bool:
    signals = page_info.get("loginSignals") or {}
    if signals.get("urlLooksLikeLogin"):
        return True
    if signals.get("hasEmailInput") and signals.get("hasPasswordInput"):
        return True
    markers = signals.get("loginMarkers") or []
    return len(markers) >= 2
