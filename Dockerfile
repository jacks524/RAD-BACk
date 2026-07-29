FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic

RUN pip install --no-cache-dir ".[test]"

EXPOSE 8000
CMD ["uvicorn", "rda.main:creer_application", "--factory", "--host", "0.0.0.0", "--port", "8000"]
