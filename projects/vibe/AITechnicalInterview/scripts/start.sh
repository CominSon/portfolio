#!/usr/bin/env bash
# Скрипт запуска локальной версии платформы
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Создаю .env из .env.example ..."
  cp .env.example .env
  echo "Отредактируйте .env при необходимости (DEEPSEEK_API_KEY опционален для первого запуска)."
fi

echo "Запуск: postgres + backend + frontend ..."
echo "Admin UI:  http://localhost:5173"
echo "API docs:  http://localhost:8000/docs"
echo ""
echo "Podman: образы backend/frontend тегируются как localhost/ai-interview-*"
echo ""

# Старые теги без localhost вызывают «Please select an image»
podman rmi aitechnicalinterview_backend:latest 2>/dev/null || true
podman rmi aitechnicalinterview_frontend:latest 2>/dev/null || true

if docker compose version >/dev/null 2>&1; then
  docker compose up --build
elif command -v podman-compose >/dev/null 2>&1; then
  podman-compose up --build
else
  echo "Ошибка: нужен «docker compose» или «podman-compose»." >&2
  exit 1
fi
