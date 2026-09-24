"""In-process workshop session owning one BrowserRuntime."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from singer_playwright.browser import BrowserConfig, BrowserRuntime
from singer_playwright.session import assert_authenticated
from singer_playwright.workshop.observe import extract_table, observe_page, resolve_target
from singer_playwright.workshop.runs import append_step_artifact, create_run_dir, write_json
from singer_playwright.workshop.recipe import RecipeExtract, build_recipe_from_steps


@dataclass
class WorkshopSessionState:
    storage_state_path: str
    headless: bool = True
    run_dir: Path | None = None
    run_id: str = ""
    step_counter: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)
    xhr_log: list[dict[str, Any]] = field(default_factory=list)
    runtime: BrowserRuntime | None = None

    def start(self) -> dict[str, Any]:
        if self.runtime is not None:
            return {"ok": True, "already_started": True, "run_id": self.run_id}

        run_dir, run_id = create_run_dir(run_id=self.run_id or None)
        self.run_dir = run_dir
        self.run_id = run_id

        config = BrowserConfig(
            storage_state_path=self.storage_state_path,
            headless=self.headless,
        )
        self.runtime = BrowserRuntime(config)
        self.runtime.start()
        self._attach_xhr_capture()
        return {"ok": True, "run_id": self.run_id, "run_dir": str(self.run_dir)}

    def stop(self) -> dict[str, Any]:
        if self.runtime is not None:
            self.runtime.stop()
            self.runtime = None
        return {"ok": True, "run_id": self.run_id}

    @property
    def page(self):
        if self.runtime is None:
            msg = "Workshop session not started"
            raise RuntimeError(msg)
        return self.runtime.page

    def _attach_xhr_capture(self) -> None:
        assert self.runtime is not None
        context = self.runtime.context

        def handle_response(response) -> None:  # noqa: ANN001
            try:
                if response.request.resource_type not in {"xhr", "fetch"}:
                    return
                content_type = (response.headers.get("content-type") or "").lower()
                if "json" not in content_type:
                    return
                self.xhr_log.append(
                    {
                        "url": response.url,
                        "status": response.status,
                        "method": response.request.method,
                    },
                )
                if len(self.xhr_log) > 200:
                    self.xhr_log = self.xhr_log[-200:]
            except Exception:  # noqa: BLE001 - best-effort capture
                return

        context.on("response", handle_response)

    def _record_step(self, action: dict[str, Any], observation: dict[str, Any] | None = None) -> None:
        self.step_counter += 1
        entry = {"step": self.step_counter, "action": action}
        if observation is not None:
            entry["observation"] = observation
        self.steps.append(action)
        if self.run_dir is not None:
            append_step_artifact(self.run_dir, self.step_counter, action.get("type", "step"), entry)

    def observe(
        self,
        *,
        frame_index: int | None = None,
        frame_url_pattern: str | None = None,
        label: str = "current",
    ) -> dict[str, Any]:
        observation = observe_page(
            self.page,
            frame_index=frame_index,
            frame_url_pattern=frame_url_pattern,
            xhr_log=self.xhr_log,
            label=label,
        )
        self._record_step(
            {
                "type": "observe",
                "frame_index": frame_index,
                "frame_url_pattern": frame_url_pattern,
                "label": label,
            },
            observation,
        )
        return observation

    def goto(self, url: str, *, wait_until: str = "domcontentloaded") -> dict[str, Any]:
        self.page.goto(url, wait_until=wait_until)
        result = {"type": "goto", "url": url, "current_url": self.page.url}
        self._record_step(result)
        return result

    def act(self, action: str, **params: Any) -> dict[str, Any]:  # noqa: ANN401
        if action == "click":
            target = resolve_target(
                self.page,
                frame_index=params.get("frame_index"),
                frame_url_pattern=params.get("frame_url_pattern"),
            )
            target.locator(str(params["selector"])).first.click(
                timeout=int(params.get("timeout_ms", 30_000)),
            )
            step = {"type": "click", **params}
        elif action == "fill":
            target = resolve_target(
                self.page,
                frame_index=params.get("frame_index"),
                frame_url_pattern=params.get("frame_url_pattern"),
            )
            target.locator(str(params["selector"])).first.fill(str(params["value"]))
            step = {"type": "fill", **params}
        elif action == "wait":
            self.page.wait_for_timeout(int(params.get("ms", 1000)))
            step = {"type": "sleep", **params}
        elif action == "wait_for_frame":
            pattern = str(params["url_pattern"])
            timeout_ms = int(params.get("timeout_ms", 30_000))
            deadline = time.time() + (timeout_ms / 1000)
            frame = None
            while time.time() < deadline:
                for candidate in self.page.frames:
                    if re.search(pattern, candidate.url, re.I):
                        frame = candidate
                        break
                if frame is not None:
                    break
                self.page.wait_for_timeout(500)
            if frame is None:
                msg = f"Timed out waiting for frame: {pattern}"
                raise TimeoutError(msg)
            step = {"type": "wait_for_frame", **params}
            params = {**params, "frame_url": frame.url}
        elif action == "frame_goto":
            pattern = str(params["url_pattern"])
            frame = None
            for candidate in self.page.frames:
                if re.search(pattern, candidate.url, re.I):
                    frame = candidate
                    break
            if frame is None:
                msg = f"No frame matched pattern: {pattern}"
                raise LookupError(msg)
            query_params = params.get("query_params") or {}
            if query_params:
                parsed = urlparse(frame.url)
                query = dict(parse_qsl(parsed.query))
                query.update({str(k): str(v) for k, v in query_params.items()})
                next_url = urlunparse(parsed._replace(query=urlencode(query)))
                frame.goto(next_url, wait_until="domcontentloaded")
            step = {"type": "frame_goto", **params}
        elif action == "assert_authenticated":
            assert_authenticated(self.page)
            step = {"type": "assert_authenticated"}
        else:
            msg = f"Unknown action: {action}"
            raise ValueError(msg)

        self._record_step(step)
        return {"ok": True, "action": action, "params": params}

    def extract(
        self,
        extract_type: str = "table",
        *,
        selector: str | None = None,
        frame_index: int | None = None,
        frame_url_pattern: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if extract_type != "table":
            msg = f"Unsupported extract type: {extract_type}"
            raise ValueError(msg)

        result = extract_table(
            self.page,
            selector=selector,
            frame_index=frame_index,
            frame_url_pattern=frame_url_pattern,
            limit=limit,
        )
        self._record_step(
            {
                "type": "extract",
                "extract_type": extract_type,
                "selector": selector,
                "frame_index": frame_index,
                "frame_url_pattern": frame_url_pattern,
                "limit": limit,
            },
            {"row_count": result.get("row_count"), "headers": result.get("headers")},
        )
        return result

    def screenshot(self, name: str = "screenshot") -> dict[str, Any]:
        if self.run_dir is None:
            msg = "Run directory not initialized"
            raise RuntimeError(msg)
        path = self.run_dir / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return {"ok": True, "path": str(path)}

    def save_recipe(
        self,
        *,
        brief_dict: dict[str, Any],
        extract: RecipeExtract,
        sample_records: list[dict[str, Any]],
        output_path: str | None = None,
    ) -> dict[str, Any]:
        from singer_playwright.workshop.brief import Brief, BriefBudget, BriefSuccess

        success_data = brief_dict.get("success") or {}
        budget_data = brief_dict.get("budget") or {}
        brief = Brief(
            tap=str(brief_dict.get("tap") or "unknown"),
            stream=str(brief_dict.get("stream") or "unknown"),
            start_url=str(brief_dict.get("start_url") or ""),
            hints=list(brief_dict.get("hints") or []),
            success=BriefSuccess(
                min_records=int(success_data.get("min_records", 1)),
                required_fields=list(success_data.get("required_fields") or []),
                not_login_page=bool(success_data.get("not_login_page", True)),
            ),
            budget=BriefBudget(
                max_steps=int(budget_data.get("max_steps", 20)),
                max_minutes=int(budget_data.get("max_minutes", 15)),
            ),
            variables={str(k): str(v) for k, v in (brief_dict.get("variables") or {}).items()},
        )
        recipe = build_recipe_from_steps(brief, self.steps, extract, sample_records)
        if output_path:
            path = Path(output_path)
        elif self.run_dir is not None:
            path = self.run_dir / "recipe.json"
        else:
            path = Path.cwd() / "recipe.json"
        write_json(path, recipe.to_dict())
        return {"ok": True, "path": str(path), "recipe": recipe.to_dict()}
