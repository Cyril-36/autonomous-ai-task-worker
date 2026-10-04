# Console: build the React app once; the worker serves the static files.
FROM node:22-slim AS console
WORKDIR /app/console
COPY console/package.json console/package-lock.json ./
RUN npm ci
COPY console/ ./
RUN npm run build

# Worker, sandbox apps and a headless Chromium in one image.
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/app/.venv/bin:$PATH
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
RUN playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
COPY config config
COPY sandbox sandbox
COPY scripts scripts
COPY worker worker
COPY evals evals
RUN uv sync --locked --no-dev
COPY --from=console /app/console/dist console/dist
# run as an unprivileged user (uid 1000, as hosted platforms such as Hugging Face expect);
# only the data folder is writable
RUN useradd --create-home --uid 1000 worker && mkdir -p data && chown worker:worker data
USER worker
ENV BIND_HOST=0.0.0.0 \
    WORKER_ENGINE=live \
    HOME=/home/worker
EXPOSE 8100 8101 8102
CMD ["python", "-m", "scripts.dev"]
