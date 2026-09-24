# aria-singer-playwright

Shared **Playwright + Singer SDK** framework for browser-backed taps (`PlaywrightTap`, `PlaywrightStream`, auth CLI, workshop daemon).

Site-specific taps live in **separate repos** (e.g. `aria-lighthouse`, `aria-profitsword`). They depend on this package only—not on each other.

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
singer-playwright = { git = "https://github.com/YOUR_ORG/aria-singer-playwright.git", rev = "v0.1.0" }
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

```bash
uv run python -m singer_playwright workshop start --storage-state storage_state.json --detach
uv run python -m singer_playwright workshop observe
uv run python -m singer_playwright workshop stop
```

See [`.cursor/skills/playwright-scraper-workshop/SKILL.md`](.cursor/skills/playwright-scraper-workshop/SKILL.md).

## New vendor Meltano repo

```bash
./scripts/new-vendor-repo.sh
# or: cookiecutter cookiecutter-vendor-meltano -o ..
```

See [docs/new-vendor-repo.md](docs/new-vendor-repo.md).

## Releases

Tag `v0.1.0`, `v0.2.0`, … on this repo. Consumer taps pin `rev` in `[tool.uv.sources]`.
