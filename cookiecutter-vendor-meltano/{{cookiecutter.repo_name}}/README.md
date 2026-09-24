# {{ cookiecutter.repo_name }}

Meltano project for **{{ cookiecutter.source_name }}** (`{{ cookiecutter.tap_id }}`).

Depends on [aria-singer-playwright]({{ cookiecutter.singer_playwright_git_url }}) only—not on aria-lighthouse.

## Quick start

```bash
uv sync
uv run playwright install chromium

uv run python -m singer_playwright auth \
  --url {{ cookiecutter.login_url }} \
  --out storage_state.json

uv run meltano install
uv run meltano invoke {{ cookiecutter.tap_id }} --discover
uv run meltano --environment=local run {{ cookiecutter.tap_id }} target-jsonl
```

## Workshop

See aria-singer-playwright `.cursor/skills/playwright-scraper-workshop/SKILL.md`. Add briefs under `briefs/`.
