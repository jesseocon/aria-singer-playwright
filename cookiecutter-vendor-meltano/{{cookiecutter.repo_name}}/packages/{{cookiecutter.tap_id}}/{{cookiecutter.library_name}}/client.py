"""{{ cookiecutter.source_name }} stream base."""

from __future__ import annotations

import sys
from abc import abstractmethod
from typing import TYPE_CHECKING

from singer_playwright.session import assert_authenticated
from singer_playwright.stream import PlaywrightStream

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import Iterable

    from playwright.sync_api import Page
    from singer_sdk.helpers.types import Context


class {{ cookiecutter.source_name }}Stream(PlaywrightStream):
    """Shared extraction helpers for {{ cookiecutter.source_name }}."""

    @override
    def extract_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        assert_authenticated(page)
        yield from self.extract_site_records(page, context)

    @abstractmethod
    def extract_site_records(
        self,
        page: Page,
        context: Context | None,
    ) -> Iterable[dict]:
        """Implement site-specific scraping for this stream."""
