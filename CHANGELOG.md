# Changelog

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
