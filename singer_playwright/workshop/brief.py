"""Brief schema and success evaluation for scraper workshops."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class BriefBudget:
    max_steps: int = 20
    max_minutes: int = 15


@dataclass
class BriefSuccess:
    min_records: int = 1
    required_fields: list[str] = field(default_factory=list)
    not_login_page: bool = True


@dataclass
class Brief:
    tap: str
    stream: str
    start_url: str
    hints: list[str] = field(default_factory=list)
    success: BriefSuccess = field(default_factory=BriefSuccess)
    budget: BriefBudget = field(default_factory=BriefBudget)
    variables: dict[str, str] = field(default_factory=dict)

    def render_url(self, **extra: str) -> str:
        values = {**self.variables, **extra}
        url = self.start_url
        for key, value in values.items():
            url = url.replace("{" + key + "}", value)
        return url

    def to_dict(self) -> dict[str, Any]:
        return {
            "tap": self.tap,
            "stream": self.stream,
            "start_url": self.start_url,
            "hints": self.hints,
            "success": {
                "min_records": self.success.min_records,
                "required_fields": self.success.required_fields,
                "not_login_page": self.success.not_login_page,
            },
            "budget": {
                "max_steps": self.budget.max_steps,
                "max_minutes": self.budget.max_minutes,
            },
            "variables": self.variables,
        }


def load_brief(path: str | Path) -> Brief:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"Brief must be a mapping: {path}"
        raise ValueError(msg)

    success_data = data.get("success") or {}
    budget_data = data.get("budget") or {}

    return Brief(
        tap=str(data["tap"]),
        stream=str(data["stream"]),
        start_url=str(data["start_url"]),
        hints=list(data.get("hints") or []),
        success=BriefSuccess(
            min_records=int(success_data.get("min_records", 1)),
            required_fields=list(success_data.get("required_fields") or []),
            not_login_page=bool(success_data.get("not_login_page", True)),
        ),
        budget=BriefBudget(
            max_steps=int(budget_data.get("max_steps", 20)),
            max_minutes=int(budget_data.get("max_minutes", 15)),
        ),
        variables={str(k): str(v) for k, v in (data.get("variables") or {}).items()},
    )


def evaluate_success(
    brief: Brief,
    *,
    records: list[dict[str, Any]],
    login_page: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    record_count_ok = len(records) >= brief.success.min_records
    checks.append(
        {
            "name": "min_records",
            "passed": record_count_ok,
            "expected": brief.success.min_records,
            "actual": len(records),
        },
    )

    missing_fields: list[str] = []
    if records and brief.success.required_fields:
        sample = records[0]
        for field_name in brief.success.required_fields:
            if field_name not in sample or sample[field_name] in (None, ""):
                missing_fields.append(field_name)
    fields_ok = not missing_fields
    checks.append(
        {
            "name": "required_fields",
            "passed": fields_ok,
            "expected": brief.success.required_fields,
            "missing": missing_fields,
        },
    )

    login_ok = not brief.success.not_login_page or not login_page
    checks.append(
        {
            "name": "not_login_page",
            "passed": login_ok,
            "login_page": login_page,
        },
    )

    passed = all(check["passed"] for check in checks)
    return {"passed": passed, "checks": checks}
