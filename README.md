# aria-singer-playwright

Shared **Playwright + Singer SDK** framework for browser-backed taps (`PlaywrightTap`, `PlaywrightStream`, auth CLI, workshop daemon).

Site-specific taps live in **separate repos** (e.g. [aria-lighthouse-tap](https://github.com/jesseocon/aria-lighthouse-tap)). They depend on this package only—not on each other.

## Install as a dependency

**Local sibling checkout (development):**

```toml
# consumer pyproject.toml
[tool.uv.sources]
singer-playwright = { path = "../aria-singer-playwright", editable = true }
```

**Git tag (CI / production):**

```toml
[tool.uv.sources]
singer-playwright = { git = "https://github.com/jesseocon/aria-singer-playwright.git", rev = "v0.1.0" }
```

Then `dependencies = ["singer-playwright", …]` and `uv sync`.

## Develop the framework

```bash
cd aria-singer-playwright
uv sync
uv run pytest
```

## Auth CLI

```bash
uv run python -m singer_playwright auth --url https://example.com/login --out storage_state.json
```

## Workshop (scraper iteration)

The workshop CLI lives in this package. **Site-specific** DOM helpers belong in the Meltano project, e.g. `aria-lighthouse/workshop/page_scripts.js`.

From a tap project root (Lighthouse):

```bash
./scripts/scraper.sh start --storage-state storage_state.json --detach
./scripts/scraper.sh observe
```

Or set `MELTANO_PROJECT_ROOT` / `SINGER_PLAYWRIGHT_WORKSHOP_SCRIPTS` before `uv run python -m singer_playwright workshop …`.

See Lighthouse `.cursor/skills/playwright-scraper-workshop/SKILL.md`.

## New vendor Meltano repo

```bash
./scripts/new-vendor-repo.sh
# or: cookiecutter cookiecutter-vendor-meltano -o ..
```

See [docs/new-vendor-repo.md](docs/new-vendor-repo.md).

## Releases

Tag `v0.1.0`, `v0.3.0`, … on this repo. Consumer taps pin `rev` in `[tool.uv.sources]`.
