FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/hf-cache \
    HF_HUB_OFFLINE=0 \
    TOKENIZERS_PARALLELISM=false

WORKDIR /service

# Les modeles sont telecharges dans /hf-cache, monte depuis le disque externe : l'image reste
# legere et un redemarrage ne retelecharge rien une fois le cache chaud.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY service.py ./

EXPOSE 8082
CMD ["uvicorn", "service:application", "--host", "0.0.0.0", "--port", "8082"]
