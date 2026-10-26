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

## Run progress (aria-runner)

Every connector follows aria-runner's run-log contract (aria-runner `docs/connector-contract.md`),
so the console shows a live log and a checklist for each sync:

- Streams extend `PlaywrightStream`, which reports start, finish and failure. Use
  `self.skip(...)`, `self.progress(...)` and `self.notice(...)` for the rest.
- The connector runs each phase with a step name:
  `ctx.run_command([...meltano run...], env=env, step="extract")`, then `step="transform"` for dbt.
- The manifest declares `"progress": "v1"`.
- The connector's tests call `aria_runner.testing.assert_progress_contract(lines, streams={...})`.
- Logins queue per vendor account automatically. Give every password option a
  non-secret username field.

## Workshop

See aria-singer-playwright `.cursor/skills/playwright-scraper-workshop/SKILL.md`. Add briefs under `briefs/`.
