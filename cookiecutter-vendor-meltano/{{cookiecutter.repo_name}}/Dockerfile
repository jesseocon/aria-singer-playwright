# One vendor tap + Meltano. Build from meltano-taps parent directory:
#
#   docker build -f {{ cookiecutter.repo_name }}/Dockerfile -t {{ cookiecutter.repo_name }} .
#
# Requires sibling aria-singer-playwright copied into the image (see COPY below).

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    MELTANO_PROJECT_ROOT=/app/vendor \
    MELTANO_ENVIRONMENT=local

WORKDIR /app/vendor

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY aria-singer-playwright /app/aria-singer-playwright
COPY {{ cookiecutter.repo_name }}/pyproject.toml {{ cookiecutter.repo_name }}/meltano.yml {{ cookiecutter.repo_name }}/README.md ./
COPY {{ cookiecutter.repo_name }}/packages ./packages

RUN pip install uv && \
    uv sync && \
    uv run playwright install --with-deps chromium && \
    uv run meltano install

VOLUME ["/app/vendor/secrets"]

CMD ["uv", "run", "meltano", "--environment=local", "run", "{{ cookiecutter.tap_id }}", "target-jsonl"]
