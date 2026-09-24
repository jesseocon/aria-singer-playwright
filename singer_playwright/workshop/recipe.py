"""Replayable scraper recipes produced by the workshop loop."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.session import assert_authenticated
from singer_playwright.workshop.brief import Brief, evaluate_success, load_brief
from singer_playwright.workshop.schema import infer_schema_from_records
from singer_playwright.workshop.observe import extract_table, observe_page
from singer_playwright.workshop.runs import read_json, write_json

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page


RECIPE_VERSION = 1


@dataclass
class RecipeExtract:
    type: str = "table"
    selector: str | None = None
    frame_url_pattern: str | None = None
    frame_index: int | None = None
    limit: int = 500

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecipeExtract:
        return cls(
            type=str(data.get("type") or "table"),
            selector=data.get("selector"),
            frame_url_pattern=data.get("frame_url_pattern"),
            frame_index=data.get("frame_index"),
            limit=int(data.get("limit") or 500),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "selector": self.selector,
            "frame_url_pattern": self.frame_url_pattern,
            "frame_index": self.frame_index,
            "limit": self.limit,
        }


@dataclass
class Recipe:
    version: int
    brief: dict[str, Any]
    steps: list[dict[str, Any]] = field(default_factory=list)
    extract: RecipeExtract = field(default_factory=RecipeExtract)
    sample_records: list[dict[str, Any]] = field(default_factory=list)
    inferred_schema: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Recipe:
        return cls(
            version=int(data.get("version") or RECIPE_VERSION),
            brief=dict(data.get("brief") or {}),
            steps=list(data.get("steps") or []),
            extract=RecipeExtract.from_dict(data.get("extract") or {}),
            sample_records=list(data.get("sample_records") or []),
            inferred_schema=dict(data.get("inferred_schema") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "brief": self.brief,
            "steps": self.steps,
            "extract": self.extract.to_dict(),
            "sample_records": self.sample_records[:10],
            "inferred_schema": self.inferred_schema,
        }


def load_recipe(path: str | Path) -> Recipe:
    return Recipe.from_dict(read_json(Path(path)))


def save_recipe(path: str | Path, recipe: Recipe) -> Path:
    output = Path(path)
    write_json(output, recipe.to_dict())
    return output


def _find_frame(page: Page, url_pattern: str, *, timeout_ms: int = 30_000) -> Frame:
    pattern = re.compile(url_pattern, re.I)
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        for frame in page.frames:
            if pattern.search(frame.url):
                return frame
        page.wait_for_timeout(500)
    msg = f"Timed out waiting for frame matching: {url_pattern}"
    raise TimeoutError(msg)


def _apply_frame_query_params(frame: Frame, query_params: dict[str, str]) -> None:
    if not query_params:
        return
    parsed = urlparse(frame.url)
    query = dict(parse_qsl(parsed.query))
    query.update(query_params)
    next_url = urlunparse(parsed._replace(query=urlencode(query)))
    if next_url != frame.url:
        frame.goto(next_url, wait_until="domcontentloaded")


def _wait_for_table_script(timeout_ms: int) -> None:
    del timeout_ms


def execute_step(page: Page, step: dict[str, Any]) -> dict[str, Any]:
    step_type = step["type"]
    result: dict[str, Any] = {"type": step_type, "ok": True}

    if step_type == "goto":
        page.goto(str(step["url"]), wait_until=step.get("wait_until", "domcontentloaded"))
        result["url"] = page.url
        return result

    if step_type == "wait_for_frame":
        frame = _find_frame(page, str(step["url_pattern"]), timeout_ms=int(step.get("timeout_ms", 30_000)))
        result["frame_url"] = frame.url
        return result

    if step_type == "frame_goto":
        frame = _find_frame(page, str(step["url_pattern"]), timeout_ms=int(step.get("timeout_ms", 30_000)))
        if step.get("query_params"):
            _apply_frame_query_params(frame, {str(k): str(v) for k, v in step["query_params"].items()})
        result["frame_url"] = frame.url
        return result

    if step_type == "wait":
        deadline = time.time() + (int(step.get("timeout_ms", 90_000)) / 1000)
        poll_ms = int(step.get("poll_ms", 2000))
        frame_pattern = step.get("frame_url_pattern")
        target: Page | Frame = _find_frame(page, frame_pattern) if frame_pattern else page
        while time.time() < deadline:
            ready = target.evaluate(step["script"])
            if ready:
                result["ready"] = True
                return result
            page.wait_for_timeout(poll_ms)
        msg = step.get("error_message") or "Timed out waiting for readiness script"
        raise TimeoutError(msg)

    if step_type == "click":
        frame_pattern = step.get("frame_url_pattern")
        target: Page | Frame = _find_frame(page, frame_pattern) if frame_pattern else page
        target.locator(str(step["selector"])).first.click(timeout=int(step.get("timeout_ms", 30_000)))
        return result

    if step_type == "fill":
        frame_pattern = step.get("frame_url_pattern")
        target: Page | Frame = _find_frame(page, frame_pattern) if frame_pattern else page
        target.locator(str(step["selector"])).first.fill(str(step["value"]))
        return result

    if step_type == "sleep":
        page.wait_for_timeout(int(step.get("ms", 1000)))
        return result

    if step_type == "assert_authenticated":
        assert_authenticated(page)
        return result

    msg = f"Unknown recipe step type: {step_type}"
    raise ValueError(msg)


def run_recipe_steps(page: Page, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        try:
            step_result = execute_step(page, step)
            step_result["index"] = index
            results.append(step_result)
        except Exception as exc:  # noqa: BLE001 - surface step failures to caller
            results.append({"index": index, "type": step.get("type"), "ok": False, "error": str(exc)})
            raise
    return results


def extract_from_recipe(page: Page, extract: RecipeExtract) -> dict[str, Any]:
    if extract.type != "table":
        msg = f"Unsupported extract type: {extract.type}"
        raise ValueError(msg)
    return extract_table(
        page,
        selector=extract.selector,
        frame_index=extract.frame_index,
        frame_url_pattern=extract.frame_url_pattern,
        limit=extract.limit,
    )


def replay_recipe(
    recipe: Recipe,
    *,
    storage_state_path: str,
    headless: bool = True,
    brief_path: str | Path | None = None,
) -> dict[str, Any]:
    brief = load_brief(brief_path) if brief_path else Brief(
        tap=str(recipe.brief.get("tap") or "unknown"),
        stream=str(recipe.brief.get("stream") or "unknown"),
        start_url=str(recipe.brief.get("start_url") or ""),
    )

    runtime = BrowserRuntime(
        BrowserConfig(storage_state_path=storage_state_path, headless=headless),
    )
    runtime.start()
    try:
        page = runtime.page
        step_results = run_recipe_steps(page, recipe.steps)
        extraction = extract_from_recipe(page, recipe.extract)
        records = list(extraction.get("rows") or [])
        observation = observe_page(page, xhr_log=[])
        evaluation = evaluate_success(
            brief,
            records=records,
            login_page=bool(observation.get("login_page")),
        )
        return {
            "ok": evaluation["passed"],
            "step_results": step_results,
            "extraction": {
                "headers": extraction.get("headers"),
                "row_count": extraction.get("row_count"),
                "error": extraction.get("error"),
            },
            "evaluation": evaluation,
            "sample_records": records[:5],
        }
    finally:
        runtime.stop()


def build_recipe_from_steps(
    brief: Brief,
    steps: list[dict[str, Any]],
    extract: RecipeExtract,
    sample_records: list[dict[str, Any]],
) -> Recipe:
    return Recipe(
        version=RECIPE_VERSION,
        brief=brief.to_dict(),
        steps=steps,
        extract=extract,
        sample_records=sample_records,
        inferred_schema=infer_schema_from_records(sample_records),
    )
