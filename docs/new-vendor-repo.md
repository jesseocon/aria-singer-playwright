# New vendor Meltano repo

One **git repo = one website = one server deploy**. Vendor repos depend only on **aria-singer-playwright**, not on aria-lighthouse.

## Instantiate

From the framework repo:

```bash
cd aria-singer-playwright
chmod +x scripts/new-vendor-repo.sh
./scripts/new-vendor-repo.sh
```

Or:

```bash
cookiecutter cookiecutter-vendor-meltano -o ..
```

Prompts:

| Field | Purpose |
|-------|---------|
| `vendor_slug` | Short id (e.g. `profitsword`) |
| `repo_name` | Directory name (e.g. `aria-profitsword`) |
| `source_name` | Python class prefix (e.g. `ProfitSword`) |
| `tap_id` / `library_name` | Singer tap id and package name |
| URLs | `base_url`, `login_url`, `session_probe_url` |
| `singer_playwright_install` | `path` (local dev) or `git` (CI/production) |
| `singer_playwright_rev` | Tag when using git (default `v0.1.0`) |

Output: `../aria-<vendor>/` with `meltano.yml`, `packages/tap-<vendor>/`, Dockerfile, `.gitignore`.

## Local layout

```text
meltano-taps/
  aria-singer-playwright/    # framework (this repo)
  aria-lighthouse/           # Lighthouse only
  aria-profitsword/          # generated
  aria-costar/
```

Sibling repos pin the framework:

```toml
[tool.uv.sources]
singer-playwright = { path = "../aria-singer-playwright", editable = true }
```

## Server deploy

- Build one Docker image per vendor repo (see generated `Dockerfile`).
- Build context: **parent** `meltano-taps/` so `aria-singer-playwright` can be copied into the image.
- Mount `storage_state.json` and env at runtime; keep `.meltano` state per service.

## Bump framework version

1. Tag `aria-singer-playwright` (e.g. `v0.3.0`).
2. In each vendor repo, set `singer_playwright_rev` or update `[tool.uv.sources]` `rev`.
3. `uv sync`, run tests, redeploy.

No Lighthouse repo involvement.

## Lighthouse

`aria-lighthouse` is a normal consumer of `singer-playwright` plus Lighthouse-specific dbt/registry. Copy **patterns** from `tap-lighthouse`, not the repo itself.
