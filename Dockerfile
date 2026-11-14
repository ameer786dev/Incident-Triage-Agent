FROM ghcr.io/astral-sh/uv:0.9.18 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
COPY triage_lab ./triage_lab
COPY runbooks ./runbooks
COPY evals ./evals
COPY scripts ./scripts
RUN uv sync --frozen --no-dev
EXPOSE 8000 8001 8100
CMD ["uvicorn", "triage_lab.api:app", "--host", "0.0.0.0", "--port", "8000"]
