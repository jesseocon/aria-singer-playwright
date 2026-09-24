"""Compact page observations for agent-driven scraper iteration."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page

_SCRIPTS_PATH = Path(__file__).with_name("page_scripts.js")
_SCRIPTS_SOURCE = _SCRIPTS_PATH.read_text(encoding="utf-8")


def _evaluate_script(function_name: str, target: Page | Frame, *args: object) -> Any:
    arg_literals = ", ".join(repr(arg) for arg in args)
    expression = f"""(() => {{
        {_SCRIPTS_SOURCE}
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
    target = resolve_target(
        page,
        frame_index=frame_index,
        frame_url_pattern=frame_url_pattern,
    )

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
    }


def extract_table(
    page: Page,
    *,
    selector: str | None = None,
    frame_index: int | None = None,
    frame_url_pattern: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
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
