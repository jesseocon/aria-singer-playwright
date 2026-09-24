# {{ cookiecutter.tap_id }}

Singer tap for **{{ cookiecutter.source_name }}** via Playwright.

## Auth

```bash
uv run python -m singer_playwright auth --url {{ cookiecutter.login_url }} --out storage_state.json
```
