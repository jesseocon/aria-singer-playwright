import sys

from singer_playwright.browser import BrowserConfig, BrowserRuntime, stealth_platform

PROBE = """() => ({
  webdriver: navigator.webdriver,
  userAgent: navigator.userAgent,
  platform: navigator.platform,
  plugins: navigator.plugins.length,
})"""


def _fingerprint(*, stealth: bool) -> dict:
    with BrowserRuntime(BrowserConfig(storage_state_path=None, headless=True, stealth=stealth)) as runtime:
        headers: dict = {}

        def answer(route) -> None:  # never leaves the machine
            headers.update(route.request.headers)
            route.fulfill(status=200, content_type="text/html", body="<title>t</title>")

        runtime.page.route("https://stealth.test/**", answer)
        runtime.page.goto("https://stealth.test/")
        seen = runtime.page.evaluate(PROBE)
        seen["header_user_agent"] = headers.get("user-agent", "")
        return seen


def test_stealth_masks_automation_and_keeps_the_platform_honest() -> None:
    plain = _fingerprint(stealth=False)
    masked = _fingerprint(stealth=True)

    assert plain["webdriver"] is True
    assert "HeadlessChrome" in plain["userAgent"]

    assert not masked["webdriver"]
    assert "HeadlessChrome" not in masked["userAgent"]
    assert masked["plugins"] > 0
    assert masked["platform"] == stealth_platform()
    assert "HeadlessChrome" in plain["header_user_agent"]
    assert "HeadlessChrome" not in masked["header_user_agent"]


def test_stealth_platform_matches_the_host() -> None:
    expected = {"darwin": "MacIntel"}.get(sys.platform, "Win32" if sys.platform.startswith("win") else "Linux x86_64")
    assert stealth_platform() == expected


def test_stealth_is_off_unless_asked() -> None:
    assert BrowserConfig().stealth is False
