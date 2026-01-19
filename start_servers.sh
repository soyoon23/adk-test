#!/bin/bash
echo "================================"
echo "Starting Ollama and LiteLLM"
echo "================================"

# Ollama 시작 (포트 11435)
echo "[1/2] Starting Ollama on port 11435..."
OLLAMA_HOST=0.0.0.0:11435 /c/Users/sogeh/AppData/Local/Programs/Ollama/ollama.exe serve &

# Ollama가 준비될 때까지 대기
echo "Waiting for Ollama to be ready..."
sleep 5

# LiteLLM 시작 (포트 4000)
echo "[2/2] Starting LiteLLM on port 4000..."
cd /c/Users/sogeh/workspace/adk-test
uv run litellm --config litellm_config.yaml --port 4000 &

echo "================================"
echo "Both servers started!"
echo "- Ollama: http://localhost:11435"
echo "- LiteLLM: http://localhost:4000"
echo "================================"
