"""Sign in through enterprise SSO (PingFederate and Microsoft Entra) with a TOTP code.

Brand portals (Hilton Lobby and similar) send the browser through an identity
provider before the app. ``complete_sso`` looks at whatever page is showing and
takes the next step until ``done(page)`` is true:

email -> password -> (push prompt) "Sign in another way" -> "Use a verification
code" -> 6-digit code -> "Stay signed in?" Yes.

It never approves a push; the account must have an authenticator app registered
whose secret the tap holds. Secrets are never logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from singer_playwright.login import LoginRejected
from singer_playwright.totp import fresh_totp

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

log = logging.getLogger(__name__)

# Each step lists selectors in preference order: stable Entra ids first, then text.
# PingFederate identifier-first pages (Hilton) use name="subject" and prefill the box with "User ID".
EMAIL = (
    'input[name="loginfmt"]',
    'input[name="subject"]',
    'input[name="pf.username"]',
    'input[type="email"]',
)
PASSWORD = ('input[name="passwd"]', 'input[name="pf.pass"]', 'input[type="password"]')
SUBMIT = (
    "#idSIButton9",
    "#btnLogin",
    "#signOnButton",
    'a:has-text("Sign On")',
    'button[type="submit"]',
    'input[type="submit"]',
)
OTHER_WAY = (
    "#signInAnotherWay",
    "text=/I can.?t use my Microsoft Authenticator app right now/i",
    "text=/Sign in another way/i",
    "text=/Other ways to sign in/i",
)
USE_CODE = (
    'div[data-value="PhoneAppOTP"]',
    "text=/Use a verification code/i",
    "text=/Enter a code from/i",
)
CODE = ('input[name="otc"]', 'input[autocomplete="one-time-code"]')
CODE_SUBMIT = ("#idSubmit_SAOTCC_Continue", "#idSIButton9", 'button[type="submit"]', 'input[type="submit"]')
KMSI_CHECKBOX = ("#KmsiCheckboxField",)
KMSI_TEXT = "text=/Stay signed in\\?/i"
KMSI_YES = ("#idSIButton9", 'input[value="Yes"]', 'button:has-text("Yes")')
ERRORS = (
    "#usernameError",
    "#passwordError",
    "#idSpan_SAOTCC_Error_OTC",
    "#error.pf-error",
    "#errorText",
)


@dataclass(frozen=True)
class SsoCredentials:
    username: str
    password: str
    totp_secret: str

    def __repr__(self) -> str:  # never print secrets
        return f"SsoCredentials(username={self.username!r}, password=***, totp_secret=***)"


def _first_visible(page: Page, selectors: tuple[str, ...]) -> Locator | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible():
                return locator
        except Exception:  # noqa: BLE001 - page mid-navigation
            continue
    return None


def _click(page: Page, selectors: tuple[str, ...]) -> bool:
    target = _first_visible(page, selectors)
    if target is None:
        return False
    target.click()
    return True


def _needs_username(box: Locator, username: str) -> bool:
    """Empty, or PingFederate's "User ID" label sitting in the box as its value.

    A box the identity provider prefilled with a real account (Entra's login_hint
    carries the email when the portal user ID is a short code) is left alone.
    """
    value = box.input_value().strip()
    if not value:
        return True
    return box.get_attribute("name") == "subject" and value != username


def _error_text(page: Page) -> str | None:
    target = _first_visible(page, ERRORS)
    if target is None:
        return None
    try:
        text = target.inner_text().strip()
    except Exception:  # noqa: BLE001
        return None
    return text or None


def complete_sso(
    page: Page,
    creds: SsoCredentials,
    *,
    done: Callable[[Page], bool],
    timeout_s: float = 180,
    poll_ms: int = 500,
) -> None:
    """Drive the identity provider pages on ``page`` until ``done(page)``."""
    deadline = time.monotonic() + timeout_s
    codes_sent = 0
    last_code_window = -1
    while time.monotonic() < deadline:
        if done(page):
            return
        error = _error_text(page)
        if error:
            raise LoginRejected(f"Sign-in rejected: {error}")

        code_box = _first_visible(page, CODE)
        if code_box is not None:
            window = int(time.time() // 30)
            if codes_sent >= 2:
                raise LoginRejected("Verification code was not accepted twice; check the TOTP secret")
            if window != last_code_window:
                code_box.fill(fresh_totp(creds.totp_secret))
                last_code_window = int(time.time() // 30)
                codes_sent += 1
                log.info("SSO: entered verification code")
                _click(page, CODE_SUBMIT)
                page.wait_for_timeout(1500)
                continue
            page.wait_for_timeout(poll_ms)  # this window's code is already in; wait for the result
            continue

        if _first_visible(page, KMSI_CHECKBOX) is not None or _first_visible(page, (KMSI_TEXT,)) is not None:
            checkbox = _first_visible(page, KMSI_CHECKBOX)
            if checkbox is not None and not checkbox.is_checked():
                checkbox.check()
            if _click(page, KMSI_YES):
                log.info("SSO: stay signed in")
                page.wait_for_timeout(1500)
                continue

        if _click(page, USE_CODE):
            log.info("SSO: chose verification code")
            page.wait_for_timeout(1000)
            continue
        if _click(page, OTHER_WAY):
            log.info("SSO: declined push, signing in another way")
            page.wait_for_timeout(1000)
            continue

        password_box = _first_visible(page, PASSWORD)
        email_box = _first_visible(page, EMAIL)
        if email_box is not None and _needs_username(email_box, creds.username):
            email_box.fill(creds.username)
            if password_box is not None:  # PingFederate shows both on one form
                password_box.fill(creds.password)
            log.info("SSO: entered username")
            _click(page, SUBMIT)
            page.wait_for_timeout(1500)
            continue
        if password_box is not None and not password_box.input_value():
            password_box.fill(creds.password)
            log.info("SSO: entered password")
            _click(page, SUBMIT)
            page.wait_for_timeout(1500)
            continue

        page.wait_for_timeout(poll_ms)
    msg = f"SSO did not finish within {timeout_s:.0f}s (stuck at {page.url.split('?')[0]})"
    raise LoginRejected(msg)
