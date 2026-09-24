"""{{ cookiecutter.source_name }} streams."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from singer_sdk import typing as th

from {{ cookiecutter.library_name }}.client import {{ cookiecutter.source_name }}Stream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context


class ExampleStream({{ cookiecutter.source_name }}Stream):
    """Replace with a real stream."""

    name = "example"
    primary_keys = ("id",)
    replication_key = None
    schema = th.PropertiesList(
        th.Property("id", th.StringType, required=True),
        th.Property("value", th.StringType),
    ).to_dict()

    @override
    def extract_site_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        page.goto("{{ cookiecutter.base_url }}", wait_until="domcontentloaded")
        # TODO: implement extraction
        yield {"id": "example-1", "value": page.title()}
