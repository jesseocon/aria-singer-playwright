---
name: playwright-scraper-workshop
description: >-
  Build and iterate Playwright Singer tap streams using the in-repo workshop
  daemon. Use when the user wants to scrape a page, add a stream, explore
  authenticated SPAs or iframes, or says "workshop", "scrape this page", or
  gives a URL plus navigation hints.
---

# Playwright Scraper Workshop

## Rules

1. **Use the workshop CLI**, not the Cursor IDE browser, for authenticated sites and iframe content.
2. **Never attempt login or 2FA.** If session is invalid, stop and tell the user to run auth.
3. **Do not ask the user for selectors mid-loop.** Observe, act, extract, evaluate, repeat.
4. **Persist artifacts** under `workshop-runs/<run_id>/` every step.
5. **Replay before codegen.** A recipe must pass `recipe replay` against the brief.

## Prerequisites

```bash
uv sync
uv run playwright install chromium
uv run python -m singer_playwright auth --url https://app.mylighthouse.com/login --out storage_state.json
```

## Closed loop

### 1. Draft or load a brief

Create `briefs/<stream>.yaml` if the user only gave prose:

```yaml
tap: tap-lighthouse
stream: market-segments-snapshot
start_url: https://app.mylighthouse.com/hotel/{hotel_id}/day-by-day/market-segments
variables:
  hotel_id: "202158"
hints:
  - Same Spider iframe as strategy-snapshot
success:
  min_records: 30
  required_fields: [date]
  not_login_page: true
budget:
  max_steps: 20
  max_minutes: 15
```

### 2. Start workshop daemon

```bash
uv run python -m singer_playwright workshop start --storage-state storage_state.json --detach
```

Session metadata: `.workshop/session.json`

### 3. Observe → act → extract → evaluate

```bash
# Navigate
uv run python -m singer_playwright workshop goto --url "$(python -c "from singer_playwright.workshop.brief import load_brief; b=load_brief('briefs/strategy-snapshot.yaml'); print(b.render_url())")"

# Observe main page
uv run python -m singer_playwright workshop observe --label main

# Observe Spider iframe
uv run python -m singer_playwright workshop observe --frame-url-pattern 'spider\.kriyarevgen\.com'

# Actions
uv run python -m singer_playwright workshop act wait_for_frame --url-pattern 'spider\.kriyarevgen\.com/dashboards/day-by-day'
uv run python -m singer_playwright workshop act frame_goto --url-pattern 'spider\.kriyarevgen\.com' --query-params '{"asof":"2026-09-15","pickupFrom":"2026-09-15"}'

# Extract candidate records
uv run python -m singer_playwright workshop extract --frame-url-pattern 'spider\.kriyarevgen\.com' --selector 'table.analytics.day-by-day' --limit 50

# Evaluate against brief
uv run python -m singer_playwright workshop evaluate --brief briefs/strategy-snapshot.yaml --records '[{"date":"2026-01-01"}]' 
```

On failure: screenshot, write hypothesis to `workshop-runs/<run_id>/steps/`, try URL params before clicks, try iframe observation before main page.

### 4. Save recipe

```bash
uv run python -m singer_playwright workshop recipe save \
  --brief briefs/strategy-snapshot.yaml \
  --records '[...sample...]' \
  --frame-url-pattern 'spider\.kriyarevgen\.com/dashboards/day-by-day' \
  --selector 'table.analytics.day-by-day'
```

### 5. Replay (cold browser gate)

```bash
uv run python -m singer_playwright workshop recipe replay \
  --recipe workshop-runs/<run_id>/recipe.json \
  --brief briefs/strategy-snapshot.yaml \
  --storage-state storage_state.json
```

### 6. Codegen stream scaffolding

```bash
uv run python -m singer_playwright workshop codegen \
  --recipe workshop-runs/<run_id>/recipe.json \
  --output-dir packages/tap-lighthouse/tap_lighthouse
```

Then integrate generated stream into `tap.py` and `meltano.yml`.

### 7. Stop daemon

```bash
uv run python -m singer_playwright workshop stop
```

## Escalate to the user only when

- `ReAuthRequiredError` or login page detected after auth should be valid
- Captcha or manual 2FA required
- Budget exhausted (`max_steps` / `max_minutes`)
- Goal is underspecified (no target entity, no success criteria inferable)

## Reference fixtures

- Brief: [briefs/strategy-snapshot.yaml](../../briefs/strategy-snapshot.yaml)
- Recipe fixture (tests): [tests/fixtures/strategy-snapshot.recipe.json](../../../tests/fixtures/strategy-snapshot.recipe.json)
- Local recipes from `workshop recipe save` → `workshop-recipes/` (gitignored)

## Production tap layout

Follow existing `tap-lighthouse` structure:

- `client.py` — site stream base
- `navigation.py` — URL/frame navigation
- `export.py` — table or bundle extraction
- `streams.py` — stream class + schema with `additional_properties`

Generated code lands in `tap_lighthouse/generated/` until manually merged.
