FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    DEMO_DATABASE_PATH=/tmp/demodirector/projects.db

WORKDIR /app

COPY packages/contracts /app/packages/contracts
COPY services/worker /app/services/worker
COPY services/api /app/services/api

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-inter \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir \
    /app/packages/contracts \
    /app/services/worker \
    /app/services/api \
    && python -m playwright install --with-deps chromium \
    && mkdir -p /tmp/demodirector

CMD ["sh", "-c", "exec uvicorn demodirector_api.main:app --host 0.0.0.0 --port ${PORT}"]
