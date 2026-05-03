# syntax=docker/dockerfile:1.6
#
# Tostado Restaurant Group — backend image.
# Build:
#     docker build -t tostado-rag .
# Build with voice (Whisper STT) baked in:
#     docker build -t tostado-rag --build-arg INSTALL_VOICE=true .

ARG INSTALL_VOICE=false

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install ffmpeg only when voice is enabled (it's the largest extra dep).
ARG INSTALL_VOICE
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && if [ "$INSTALL_VOICE" = "true" ]; then \
        apt-get install -y --no-install-recommends ffmpeg; \
    fi \
 && rm -rf /var/lib/apt/lists/*

# Python deps — install base requirements first to maximise cache reuse.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY requirements-voice.txt .
RUN if [ "$INSTALL_VOICE" = "true" ]; then \
        pip install -r requirements-voice.txt; \
    fi

# App source
COPY backend/  ./backend/
COPY frontend/ ./frontend/
COPY scripts/  ./scripts/
COPY docker-entrypoint.sh ./

RUN chmod +x docker-entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["python", "-m", "backend.app"]
