"""Password login submits once, then once more if challenged."""

from __future__ import annotations

import pytest

from singer_playwright.login import LoginRejected, apply_credentials


class _Locator:
    def __init__(self, page: _Page, kind: str) -> None:
        self.page = page
        self.kind = kind

    @property
    def first(self) -> _Locator:
        return self

    def count(self) -> int:
        return 1 if self.page.visible(self.kind) else 0

    def is_visible(self) -> bool:
        return self.page.visible(self.kind)

    def fill(self, value: str) -> None:
        self.page.fills.append((self.kind, value))

    def click(self) -> None:
        if self.kind == "end":
            self.page.end_session()
            return
        self.page.submit()

    def wait_for(self, **_kwargs: object) -> None:
        if not self.is_visible():
            msg = self.kind
            raise TimeoutError(msg)


class _Page:
    def __init__(self, stages: list[set[str]]) -> None:
        self.stages = stages
        self.index = 0
        self.fills: list[tuple[str, str]] = []
        self.submits = 0
        self.ends = 0

    def visible(self, kind: str) -> bool:
        stage = self.stages[self.index]
        if kind == "form":
            return "username" in stage or "password" in stage
        return kind in stage

    def goto(self, url: str, **_kwargs: object) -> None:
        self.url = url

    def locator(self, selector: str) -> _Locator:
        if "password" in selector and "email" in selector:
            kind = "form"
        elif "verify" in selector:
            kind = "verify"
        elif "already" in selector or "another session" in selector:
            kind = "existing"
        elif "Log out" in selector or "End session" in selector or "Sign out" in selector:
            kind = "end"
        elif "password" in selector:
            kind = "password"
        elif "email" in selector or "username" in selector:
            kind = "username"
        else:
            kind = "submit"
        return _Locator(self, kind)

    def wait_for_function(self, _script: str, **_kwargs: object) -> None:
        return None

    def submit(self) -> None:
        self.submits += 1
        if self.index + 1 < len(self.stages):
            self.index += 1

    def end_session(self) -> None:
        self.ends += 1
        if self.index + 1 < len(self.stages):
            self.index += 1


def test_password_login_submits_the_form_once() -> None:
    page = _Page([{"username", "password"}, set()])

    apply_credentials(
        page,  # type: ignore[arg-type]
        username="user",
        password="secret",
        login_url="https://product.costar.com/",
    )

    assert page.submits == 1
    assert ("username", "user") in page.fills
    assert ("password", "secret") in page.fills


def test_verify_prompt_submits_the_password_once_more() -> None:
    page = _Page([{"username", "password"}, {"password", "verify"}, set()])

    apply_credentials(
        page,  # type: ignore[arg-type]
        username="user",
        password="secret",
        login_url="https://product.costar.com/",
    )

    assert page.submits == 2
    assert [value for kind, value in page.fills if kind == "password"] == ["secret", "secret"]


def test_rejected_password_stops() -> None:
    page = _Page([{"username", "password"}, {"password", "verify"}, {"password", "verify"}])

    with pytest.raises(LoginRejected):
        apply_credentials(
            page,  # type: ignore[arg-type]
            username="user",
            password="secret",
            login_url="https://product.costar.com/",
        )

    assert page.submits == 2


def test_existing_session_logs_out_once_then_signs_in() -> None:
    page = _Page([{"username", "password"}, {"existing", "end"}, {"username", "password"}, set()])

    apply_credentials(
        page,  # type: ignore[arg-type]
        username="user",
        password="secret",
        login_url="https://product.costar.com/",
    )

    assert page.ends == 1
    assert page.submits == 2


def test_existing_session_stops_when_it_remains() -> None:
    page = _Page(
        [
            {"username", "password"},
            {"existing", "end"},
            {"username", "password"},
            {"existing", "end"},
        ]
    )

    with pytest.raises(LoginRejected, match="active session"):
        apply_credentials(
            page,  # type: ignore[arg-type]
            username="user",
            password="secret",
            login_url="https://product.costar.com/",
        )

    assert page.ends == 1
    assert page.submits == 2
