"""Schema inference from extracted records."""

from __future__ import annotations

from typing import Any


def infer_schema_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "record_hash": {"type": ["string"]},
    }
    if not records:
        return {"type": "object", "properties": properties, "additionalProperties": True}

    sample = records[0]
    for key, value in sample.items():
        if key == "record_hash":
            continue
        if value is None or value == "":
            properties[key] = {"type": ["string", "null"]}
        elif isinstance(value, bool):
            properties[key] = {"type": ["boolean", "null"]}
        elif isinstance(value, int) and not isinstance(value, bool):
            properties[key] = {"type": ["integer", "string", "null"]}
        elif isinstance(value, float):
            properties[key] = {"type": ["number", "string", "null"]}
        else:
            properties[key] = {"type": ["string", "null"]}

    return {
        "type": "object",
        "properties": properties,
        "additionalProperties": True,
    }
