#!/usr/bin/env bash
#
# Bootstraps the container on each start:
#   1. Wait for Ollama to be reachable.
#   2. Make sure the LLM is pulled.
#   3. Generate the synthetic dataset if /app/data is empty.
#   4. Hand off to the Flask app (or whatever was passed as CMD).

set -euo pipefail

OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:3b}"

echo "[entrypoint] Waiting for Ollama at ${OLLAMA_HOST}..."
for i in $(seq 1 60); do
    if curl -sf "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
        echo "[entrypoint] Ollama is up."
        break
    fi
    sleep 2
    if [ "$i" = "60" ]; then
        echo "[entrypoint] WARNING: timed out waiting for Ollama."
    fi
done

# Pull the model if it isn't already there.
if ! curl -sf "${OLLAMA_HOST}/api/tags" | grep -q "\"${OLLAMA_MODEL}\""; then
    echo "[entrypoint] Pulling model ${OLLAMA_MODEL} (first run only, ~2GB)..."
    curl -s "${OLLAMA_HOST}/api/pull" -d "{\"name\":\"${OLLAMA_MODEL}\"}" >/dev/null || true
fi

# Seed the dataset if /app/data does not contain stores.json.
if [ ! -f /app/data/stores.json ]; then
    echo "[entrypoint] No dataset detected — running scripts/generate_data.py..."
    python scripts/generate_data.py
fi

echo "[entrypoint] Starting application: $*"
exec "$@"
