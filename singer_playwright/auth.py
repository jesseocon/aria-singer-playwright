"""Interactive auth bootstrap — save Playwright storage_state after manual login."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


def run_interactive_auth(
    *,
    login_url: str,
    output_path: str,
    success_url_pattern: str | None = None,
    timeout_ms: int = 300_000,
) -> Path:
    """Open a headed browser for manual login and persist storage_state.

    Args:
        login_url: Page to open for sign-in.
        output_path: Where to write storage_state.json.
        success_url_pattern: Optional regex; when matched, auth is considered complete.
        timeout_ms: Max wait for success URL after opening login page.

    Returns:
        Resolved output path.
    """
    out = Path(output_path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1600, "height": 1000})
        page = context.new_page()

        print(f"Opening {login_url} — complete login (including 2FA) in the browser window.")
        page.goto(login_url, wait_until="domcontentloaded")

        if success_url_pattern:
            page.wait_for_url(success_url_pattern, timeout=timeout_ms)
        else:
            print(
                "Press Enter in this terminal after you have finished logging in "
                "and see the authenticated app…",
            )
            input()

        context.storage_state(path=str(out))
        print(f"Saved storage_state to {out}")

        context.close()
        browser.close()

    return out
