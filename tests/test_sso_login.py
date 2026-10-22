"""TOTP codes and the SSO walk-through against a local imitation of the Entra pages."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import pytest

from singer_playwright.login import LoginRejected
from singer_playwright.sso_login import SsoCredentials, complete_sso
from singer_playwright.totp import totp

# RFC 6238 appendix B, SHA-1 seed "12345678901234567890" in base32.
RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
SECRET = "JBSWY3DPEHPK3PXP"


@pytest.mark.parametrize(
    ("at", "code"),
    [(59, "94287082"), (1111111109, "07081804"), (1234567890, "89005924"), (2000000000, "69279037")],
)
def test_totp_matches_rfc_vectors(at: int, code: str) -> None:
    assert totp(RFC_SECRET, at=at, digits=8) == code


def test_totp_accepts_spaced_lowercase_secret() -> None:
    assert totp("jbsw y3dp ehpk 3pxp", at=59) == totp(SECRET, at=59)
    with pytest.raises(ValueError, match="base32"):
        totp("not base32 !!", at=59)


def test_credentials_repr_hides_secrets() -> None:
    text = repr(SsoCredentials("me@example.com", "hunter2", SECRET))
    assert "hunter2" not in text and SECRET not in text


PAGE = "<html><body>{}</body></html>"
PAGES = {
    # Hilton's PingFederate identifier-first page: value prefilled with "User ID", image submit.
    "/ping": '<form method="post" action="/login">Please enter your User ID.'
    '<input id="identifierInput" name="subject" type="text" value="User ID">'
    '<input id="btnLogin" name="btnLogin" type="image" alt="Next"></form>',
    "/login":'<form method="post" action="/password"><input name="loginfmt" type="email">'
    '<input id="idSIButton9" type="submit" value="Next"></form>',
    "/password": '<form method="post" action="/push"><input name="passwd" type="password">'
    '<input id="idSIButton9" type="submit" value="Sign in"></form>',
    "/push": '<div>Approve sign in request. Enter the number shown.</div>'
    '<a id="signInAnotherWay" href="/proofs">I can\'t use my Microsoft Authenticator app right now</a>',
    "/proofs": '<div data-value="PhoneAppNotification">Approve a request</div>'
    '<div data-value="PhoneAppOTP" onclick="location=\'/otc\'">Use a verification code</div>',
    "/otc": '<form method="post" action="/check"><input name="otc">{error}'
    '<input id="idSubmit_SAOTCC_Continue" type="submit" value="Verify"></form>'
    '<a id="signInAnotherWay" href="/proofs">Sign in another way</a>',
    "/kmsi": '<div>Stay signed in?</div><form method="post" action="/done">'
    '<input id="KmsiCheckboxField" type="checkbox"><input id="idSIButton9" type="submit" value="Yes"></form>',
    "/done": "<h1>Lobby</h1>",
}


def _site(secret: str, seen: dict[str, str]) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def _html(self, body: str) -> None:
            data = PAGE.format(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            self._html(PAGES.get(self.path, "").replace("{error}", ""))

        def do_POST(self) -> None:  # noqa: N802
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"] or 0)).decode()).items()}
            seen.update(form)
            if self.path == "/check":
                if form.get("otc") == totp(secret):
                    self._html('<script>location="/kmsi"</script>')
                else:
                    self._html(
                        PAGES["/otc"].replace("{error}", '<div id="idSpan_SAOTCC_Error_OTC">You entered the wrong code</div>')
                    )
                return
            self._html(PAGES.get(self.path, "").replace("{error}", ""))

    return Handler


@pytest.fixture
def browser_page() -> Iterator:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch()
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"chromium unavailable: {exc}")
        page = browser.new_page()
        yield page
        browser.close()


def _serve(secret: str, seen: dict[str, str]) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _site(secret, seen))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


def test_walks_entra_pages_with_a_code(browser_page) -> None:
    seen: dict[str, str] = {}
    server, base = _serve(SECRET, seen)
    try:
        browser_page.goto(f"{base}/login")
        complete_sso(
            browser_page,
            SsoCredentials("me@example.com", "pw", SECRET),
            done=lambda p: p.url.endswith("/done"),
            timeout_s=30,
        )
    finally:
        server.shutdown()
    assert seen["loginfmt"] == "me@example.com"
    assert seen["passwd"] == "pw"


def test_ping_identifier_page_with_prefilled_label(browser_page) -> None:
    seen: dict[str, str] = {}
    server, base = _serve(SECRET, seen)
    try:
        browser_page.goto(f"{base}/ping")
        complete_sso(
            browser_page,
            SsoCredentials("me@example.com", "pw", SECRET),
            done=lambda p: p.url.endswith("/done"),
            timeout_s=30,
        )
    finally:
        server.shutdown()
    assert seen["subject"] == "me@example.com"
    assert seen["loginfmt"] == "me@example.com"


def test_wrong_secret_stops_with_the_page_error(browser_page) -> None:
    server, base = _serve(SECRET, {})
    try:
        browser_page.goto(f"{base}/login")
        with pytest.raises(LoginRejected, match="wrong code"):
            complete_sso(
                browser_page,
                SsoCredentials("me@example.com", "pw", "GEZDGNBVGY3TQOJQ"),
                done=lambda p: p.url.endswith("/done"),
                timeout_s=30,
            )
    finally:
        server.shutdown()
