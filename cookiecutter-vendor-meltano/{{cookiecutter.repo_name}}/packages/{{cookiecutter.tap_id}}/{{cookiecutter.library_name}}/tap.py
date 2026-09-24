"""{{ cookiecutter.source_name }} tap."""

from __future__ import annotations

import sys

from singer_sdk import typing as th

from singer_playwright.tap import PlaywrightTap
from {{ cookiecutter.library_name }} import streams

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


class Tap{{ cookiecutter.source_name }}(PlaywrightTap):
    name = "{{ cookiecutter.tap_id }}"

    config_jsonschema = th.PropertiesList(
        th.Property(
            "storage_state_path",
            th.StringType(nullable=False),
            required=True,
            secret=True,
        ),
        th.Property(
            "base_url",
            th.StringType(nullable=False),
            default="{{ cookiecutter.base_url }}",
        ),
        th.Property(
            "session_probe_url",
            th.StringType(nullable=False),
            default="{{ cookiecutter.session_probe_url }}",
        ),
        th.Property(
            "headless",
            th.BooleanType(nullable=False),
            default=True,
        ),
        th.Property(
            "rate_limit_seconds",
            th.NumberType(nullable=False),
            default=5.0,
        ),
    ).to_dict()

    @override
    def discover_streams(self) -> list[streams.ExampleStream]:
        return [streams.ExampleStream(self)]


if __name__ == "__main__":
    Tap{{ cookiecutter.source_name }}.cli()
