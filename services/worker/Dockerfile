FROM mcr.microsoft.com/playwright/python:v1.62.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY packages/contracts /app/packages/contracts
COPY services/worker /app/services/worker
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-inter \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir /app/packages/contracts /app/services/worker
CMD ["sh", "-c", "exec uvicorn demodirector_worker.app:app --host 0.0.0.0 --port ${PORT}"]
