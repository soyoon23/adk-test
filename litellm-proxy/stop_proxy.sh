#!/bin/bash
echo "================================"
echo "Stopping Ollama and LiteLLM"
echo "================================"

# Ollama 종료
echo "[1/2] Stopping Ollama..."
taskkill //IM ollama.exe //F 2>/dev/null || echo "Ollama was not running."

# LiteLLM 종료 (포트 4000 사용 중인 프로세스)
echo "[2/2] Stopping LiteLLM..."
PID=$(netstat -ano | grep :4000 | grep LISTENING | awk '{print $5}')
if [ -n "$PID" ]; then
    taskkill //PID $PID //F 2>/dev/null
    echo "LiteLLM stopped."
else
    echo "LiteLLM was not running."
fi

echo "================================"
echo "All servers stopped!"
echo "================================"
