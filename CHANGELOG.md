# Changelog

## v0.11.0

- A login's own proxy: aria-runner sets `ARIA_PROXY_URL` (`http://user:pass@host:port`) for every
  run on a login that has one, and `launch_chromium` gives it to both engines (Playwright and
  patchright). Before the browser is handed back, a page in a throwaway context asks
  api.ipify.org (then ifconfig.me) for the exit IP. No answer raises `ProxyUnavailable`; an IP
  other than `ARIA_PROXY_EXPECTED_IP` raises `ProxyMismatch`. Both are `ProxyError`, never retried,
  and never name the proxy's username or password. The exit IP is reported as a `proxy` notice.
- `ARIA_BROWSER_TIMEZONE` now applies under the standard engine too (the context's
  `timezone_id`); max stealth keeps setting Chrome's own `TZ`.

## v0.7.0

- Video of a run's browser: when aria-runner starts a run with "record video" it sets
  `ARIA_RECORD_VIDEO=1`, and `BrowserRuntime` records every page (1280x800 WebM). When the browser
  closes, each recording moves into the run's `ARIA_SCREENSHOT_DIR` and a notice names it
  (`code: video`, `video: <file>`), so the runner uploads it and the console plays it. Nothing is
  recorded otherwise. `BrowserRuntime(config, logger)` takes the tap's logger for that notice;
  `PlaywrightTap` passes its own.

## v0.6.0

- Stealth (playwright-stealth 2.0.3), off by default: `BrowserConfig(stealth=True)`, the tap setting
  `stealth: true`, or `workshop start --stealth`. It hides the signs of an automated browser
  (`navigator.webdriver`, the HeadlessChrome user agent in the page and in request headers, empty
  plugins, WebGL vendor, and so on). `navigator.platform` follows the host (Linux x86_64 in Cloud Run)
  so it agrees with the user agent; stealth's own default is Win32.

## v0.5.0

- `singer_playwright.errors.TransientError`: raise it (or any exception with `retryable = True`)
  once a tap's own retries have run out on a failure that usually clears up (a rate limit, a
  vendor outage). The stream's error event says `"retryable": true`, and aria-runner (0.1.29)
  queues the run again later instead of treating it as permanent.

## v0.4.0

- `singer_playwright.codes.wait_for_code(address, after=...)`: the newest sign-in code a vendor
  emailed to the login's code inbox since `after`, handed over once by aria-runner's code
  broker (runner 0.1.24). For logins with an emailed one-time code, such as Okta's email factor.

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
