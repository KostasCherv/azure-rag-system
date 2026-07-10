FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH \
    PORT=8000

RUN groupadd --system app && useradd --system --gid app --create-home app
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev --no-install-project
COPY azure_rag ./azure_rag
COPY main.py ./
RUN chown -R app:app /app

USER app
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn azure_rag.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
