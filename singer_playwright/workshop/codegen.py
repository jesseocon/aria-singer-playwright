"""Compile a workshop recipe into Singer stream scaffolding."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from singer_playwright.workshop.recipe import Recipe, load_recipe
from singer_playwright.workshop.schema import infer_schema_from_records


def _snake(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()
    return value or "stream"


def _class_name(name: str) -> str:
    parts = re.split(r"[^a-zA-Z0-9]+", name)
    return "".join(part.capitalize() for part in parts if part)


def _schema_to_typing(schema: dict[str, Any]) -> str:
    lines = ["th.PropertiesList("]
    for name, spec in sorted((schema.get("properties") or {}).items()):
        types = spec.get("type") or ["string"]
        if isinstance(types, str):
            types = [types]
        nullable = "null" in types
        if name == "record_hash":
            lines.append(f'    th.Property("{name}", th.StringType, required=True),')
        elif "integer" in types:
            lines.append(
                f'    th.Property("{name}", th.IntegerType{", nullable=True" if nullable else ""}),',
            )
        elif "number" in types:
            lines.append(
                f'    th.Property("{name}", th.NumberType{", nullable=True" if nullable else ""}),',
            )
        elif "boolean" in types:
            lines.append(
                f'    th.Property("{name}", th.BooleanType{", nullable=True" if nullable else ""}),',
            )
        else:
            lines.append(
                f'    th.Property("{name}", th.StringType{", nullable=True" if nullable else ""}),',
            )
    lines.append("    additional_properties=th.StringType(nullable=True),")
    lines.append(").to_dict()")
    return "\n".join(lines)


def _render_navigation_module(stream_snake: str, recipe: Recipe) -> str:
    goto_steps = [step for step in recipe.steps if step.get("type") == "goto"]
    start_url = goto_steps[0]["url"] if goto_steps else recipe.brief.get("start_url", "")
    frame_pattern = recipe.extract.frame_url_pattern or ""
    selector = recipe.extract.selector or "table.analytics.day-by-day"

    return f'''"""Generated navigation for {recipe.brief.get("stream")}."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Frame, Page


START_URL = {start_url!r}
FRAME_URL_PATTERN = {frame_pattern!r}
TABLE_SELECTOR = {selector!r}


def get_content_frame(page: Page, *, timeout_ms: int = 30_000) -> Frame:
    pattern = re.compile(FRAME_URL_PATTERN or ".", re.I)
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        for frame in page.frames:
            if pattern.search(frame.url):
                return frame
        page.wait_for_timeout(500)
    msg = "Timed out waiting for content frame"
    raise TimeoutError(msg)


def navigate_{stream_snake}(page: Page) -> Frame:
    page.goto(START_URL, wait_until="domcontentloaded")
    frame = get_content_frame(page)
    return frame
'''


def _render_export_module(stream_snake: str, recipe: Recipe) -> str:
    selector = recipe.extract.selector or "table.analytics.day-by-day"
    return f'''"""Generated export helpers for {recipe.brief.get("stream")}."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.sync_api import Frame

TABLE_SELECTOR = {selector!r}

TABLE_EXPORT_JS = """
() => {{
  const table = document.querySelector({selector!r});
  if (!table) {{
    return {{ headers: [], rows: [], error: "table not found" }};
  }}
  const headerCells = Array.from(table.querySelectorAll("thead th"));
  const headers = headerCells.map((cell, index) => {{
    const text = (cell.textContent || "").trim().replace(/\\\\s+/g, "_").toLowerCase();
    return text || `column_${{index}}`;
  }});
  const bodyRows = Array.from(table.querySelectorAll("tbody tr"));
  const rows = bodyRows.map((row) => {{
    const cells = Array.from(row.querySelectorAll("td"));
    const record = {{}};
    cells.forEach((cell, index) => {{
      const key = headers[index] || `column_${{index}}`;
      record[key] = (cell.textContent || "").trim();
    }});
    return record;
  }});
  return {{ headers, rows, error: null }};
}}
"""


def extract_{stream_snake}_records(frame: Frame) -> list[dict[str, Any]]:
    result = frame.evaluate(TABLE_EXPORT_JS)
    if result.get("error"):
        msg = result["error"]
        raise RuntimeError(msg)
    return list(result.get("rows") or [])


def enrich_{stream_snake}_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        record = dict(row)
        record["record_hash"] = _record_hash(index, row)
        enriched.append(record)
    return enriched


def _record_hash(index: int, row: dict[str, Any]) -> str:
    payload = json.dumps({{"index": index, "row": row}}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
'''


def _render_stream_module(stream_snake: str, class_name: str, recipe: Recipe) -> str:
    schema_expr = _schema_to_typing(recipe.inferred_schema or infer_schema_from_records(recipe.sample_records))
    stream_name = recipe.brief.get("stream") or stream_snake
    return f'''"""Generated stream for {stream_name}."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from singer_sdk import typing as th

from tap_lighthouse.client import LighthouseStream
from tap_lighthouse.generated.{stream_snake}_export import enrich_{stream_snake}_records, extract_{stream_snake}_records
from tap_lighthouse.generated.{stream_snake}_navigation import navigate_{stream_snake}

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context


{stream_snake.upper()}_SCHEMA = {schema_expr}


class {class_name}Stream(LighthouseStream):
    name = {stream_name!r}
    primary_keys = ("record_hash",)
    schema = {stream_snake.upper()}_SCHEMA

    @override
    def extract_lighthouse_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        frame = navigate_{stream_snake}(page)
        rows = extract_{stream_snake}_records(frame)
        yield from enrich_{stream_snake}_records(rows)
'''


def _render_test_module(stream_snake: str, class_name: str) -> str:
    return f'''"""Generated tests for {stream_snake}."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tap_lighthouse.generated.{stream_snake}_stream import {class_name}Stream
from tap_lighthouse.tap import TapLighthouse


@patch("tap_lighthouse.generated.{stream_snake}_stream.extract_{stream_snake}_records")
@patch("tap_lighthouse.generated.{stream_snake}_stream.navigate_{stream_snake}")
@patch("singer_playwright.tap.BrowserRuntime")
def test_{stream_snake}_yields_records(
    mock_runtime_cls: MagicMock,
    mock_navigate: MagicMock,
    mock_extract: MagicMock,
    tmp_path: object,
) -> None:
    state_file = tmp_path / "storage_state.json"  # type: ignore[operator]
    state_file.write_text('{{"cookies": [], "origins": []}}', encoding="utf-8")

    page = MagicMock()
    frame = MagicMock()
    mock_navigate.return_value = frame
    mock_extract.return_value = [{{"date": "2026-01-01", "revenue": "100"}}]

    runtime = MagicMock()
    runtime.page = page
    mock_runtime_cls.return_value = runtime

    tap = TapLighthouse(
        config={{
            "storage_state_path": str(state_file),
            "hotel_id": "202158",
        }},
    )
    stream = {class_name}Stream(tap)
    records = list(stream.extract_lighthouse_records(page, None))

    assert len(records) == 1
    assert records[0]["record_hash"]
'''


def compile_recipe(
    recipe: Recipe,
    *,
    output_dir: str | Path,
    tap_package: str = "tap_lighthouse",
) -> dict[str, Any]:
    stream_name = str(recipe.brief.get("stream") or "stream")
    stream_snake = _snake(stream_name)
    class_name = _class_name(stream_name)

    out = Path(output_dir)
    generated = out / "generated"
    generated.mkdir(parents=True, exist_ok=True)

    files = {
        generated / f"{stream_snake}_navigation.py": _render_navigation_module(stream_snake, recipe),
        generated / f"{stream_snake}_export.py": _render_export_module(stream_snake, recipe),
        generated / f"{stream_snake}_stream.py": _render_stream_module(stream_snake, class_name, recipe),
        out / "tests" / f"test_generated_{stream_snake}.py": _render_test_module(stream_snake, class_name),
        generated / "__init__.py": "",
    }

    written: list[str] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(str(path))

    manifest = {
        "tap_package": tap_package,
        "stream": stream_name,
        "stream_snake": stream_snake,
        "class_name": class_name,
        "files": written,
        "schema": recipe.inferred_schema or infer_schema_from_records(recipe.sample_records),
        "integration_hint": (
            f"Register {class_name}Stream in tap.py discover_streams() and add meltano select/metadata."
        ),
    }
    manifest_path = generated / f"{stream_snake}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    written.append(str(manifest_path))

    return manifest


def compile_recipe_file(
    recipe_path: str | Path,
    *,
    output_dir: str | Path,
    tap_package: str = "tap_lighthouse",
) -> dict[str, Any]:
    return compile_recipe(load_recipe(recipe_path), output_dir=output_dir, tap_package=tap_package)
