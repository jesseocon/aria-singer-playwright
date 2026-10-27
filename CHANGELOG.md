# Changelog

## v0.3.0

- Screenshots for aria-runner runs: `singer_playwright.screenshots.screenshot(page, label, logger)`
  and `PlaywrightStream.screenshot(label)` save a JPEG to the run's `ARIA_SCREENSHOT_DIR` and
  report a `notice` naming it (`code: screenshot`), which the console shows in the run's log
  panel. A failing stream keeps one automatically before it reports the error. Never raises;
  outside a run nothing is saved.

## v0.2.0

- `PlaywrightStream` reports run progress for aria-runner (contract v1): each stream's start,
  finish with its row count, and failure. New `report`, `progress`, `notice` and `skip` helpers
  (`singer_playwright.progress`).
- Password login (`auth_method: password`), SSO with TOTP, Cloud Run Chromium flags, workshop
  tab following and downloads (since v0.1.0).
- Template: run progress section, `v0.2.0` pin.

## v0.1.0

- Initial release: `PlaywrightTap`, `PlaywrightStream`, auth CLI, workshop daemon.
- Vendor repo cookiecutter (`cookiecutter-vendor-meltano`).
