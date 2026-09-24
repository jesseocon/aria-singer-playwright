# cookiecutter-vendor-meltano

Scaffold a **standalone Meltano project** for one vendor site (one tap, one deploy).

```bash
cd aria-singer-playwright
cookiecutter cookiecutter-vendor-meltano -o ..
```

Creates `../aria-<vendor>/` with `meltano.yml`, root `pyproject.toml`, and `packages/tap-<vendor>/`.
