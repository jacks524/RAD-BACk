FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl espeak-ng ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic ./alembic
# Sans alembic.ini, « alembic upgrade head » echoue dans le conteneur avec
# « No 'script_location' key found » — or c'est la commande que documente le README.
COPY alembic.ini ./

# Connexion lente et instable sur ce poste : sans ces reglages, un telechargement coupe
# (« Connection broken: BrokenPipeError ») fait echouer tout le build.
RUN pip install --no-cache-dir --retries 10 --timeout 120 ".[test]"

EXPOSE 8000
CMD ["uvicorn", "rda.main:creer_application", "--factory", "--host", "0.0.0.0", "--port", "8000"]
