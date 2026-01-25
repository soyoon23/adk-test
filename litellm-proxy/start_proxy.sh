#!/bin/bash
echo "================================"
echo "Starting Ollama and LiteLLM Proxy"
echo "================================"

# Load env vars from litellm-proxy/.env (supports "KEY = \"value\"" with spaces)
ENV_FILE="/c/Users/sogeh/workspace/adk-test/litellm-proxy/.env"
if [ -f "$ENV_FILE" ]; then
  while IFS= read -r line; do
    case "$line" in
      ""|\#*) continue ;;
    esac
    key="$(echo "$line" | cut -d= -f1 | tr -d '[:space:]')"
    val="$(echo "$line" | cut -d= -f2- | sed -E 's/^[[:space:]]+|[[:space:]]+$//g; s/^"//; s/"$//')"
    if [ -n "$key" ]; then
      export "$key=$val"
    fi
  done < "$ENV_FILE"
fi

# Ollama 시작 (포트 11435)
echo "[1/2] Starting Ollama on port 11435..."
OLLAMA_HOST=0.0.0.0:11435 /c/Users/sogeh/AppData/Local/Programs/Ollama/ollama.exe serve &

# Ollama가 준비될 때까지 대기
echo "Waiting for Ollama to be ready..."
sleep 5

# LiteLLM Proxy 시작 (포트 4000)
echo "[2/2] Starting LiteLLM Proxy on port 4000..."
cd /c/Users/sogeh/workspace/adk-test/litellm-proxy
uv run litellm --config litellm_config.yaml --port 4000 &

echo "================================"
echo "Both servers started!"
echo "- Ollama: http://localhost:11435"
echo "- LiteLLM Proxy: http://localhost:4000"
echo "================================"
