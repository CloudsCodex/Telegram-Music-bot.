# Developer by : Mr_Manas_Op
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .

# ffmpeg is required at runtime; build tools are only needed to compile TgCrypto if no wheel exists.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates build-essential \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN useradd --create-home --uid 10001 musicbot \
    && mkdir -p /app/data /app/logs \
    && chown -R musicbot:musicbot /app
USER musicbot

CMD ["python", "main.py"]
