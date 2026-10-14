FROM python:3.12-slim

# git is needed to install the AP2 SDK from GitHub.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev

COPY travelin ./travelin

ENV PATH="/app/.venv/bin:$PATH" PORT=8080
CMD ["sh", "-c", "uvicorn travelin.main:app --host 0.0.0.0 --port ${PORT}"]
