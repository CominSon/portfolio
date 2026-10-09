#!/usr/bin/env bash
# Временный публичный URL *.trycloudflare.com без REG.RU DNS.
# Нужен запущенный ./scripts/run-local.sh (frontend на :5173).
#
# ВАЖНО: URL живёт только пока работает этот процесс. После Ctrl+C старый адрес
# (в закладках и .env) перестаёт открываться — запустите скрипт снова.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
URL_FILE="$ROOT/.quick-tunnel-url"
ENV_FILE="$ROOT/.env"
UPDATE_ENV="${UPDATE_ENV:-1}"

export PATH="${HOME}/.local/bin:${PATH}"
CF="${CF:-$(command -v cloudflared || true)}"
[[ -x "${HOME}/.local/bin/cloudflared" ]] && CF="${HOME}/.local/bin/cloudflared"

if [[ -z "$CF" ]]; then
  echo "Сначала: ./scripts/install-cloudflared.sh"
  exit 1
fi

if ! curl -sf --connect-timeout 2 http://127.0.0.1:5173/ >/dev/null 2>&1; then
  echo "!!! Frontend не отвечает на http://127.0.0.1:5173"
  echo "    Сначала в другом терминале: ./scripts/run-local.sh"
  exit 1
fi

echo "Быстрый туннель → http://127.0.0.1:5173"
echo "Ждите строку https://….trycloudflare.com (обычно 5–15 с)"
echo ""

saved_url=""
save_url() {
  local url="$1"
  [[ -z "$url" || "$url" == "$saved_url" ]] && return
  saved_url="$url"
  echo "$url" >"$URL_FILE"
  echo ""
  echo "════════════════════════════════════════════════════════════"
  echo "  Актуальный URL: $url"
  echo "  Файл: .quick-tunnel-url"
  echo "════════════════════════════════════════════════════════════"
  echo "  1) Откройте админку по этому URL (не localhost, не старый trycloudflare)"
  echo "  2) Сгенерируйте ссылку на интервью заново"
  if [[ "$UPDATE_ENV" == "1" && -f "$ENV_FILE" ]]; then
    sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$url|" "$ENV_FILE"
    sed -i "s|^PUBLIC_FRONTEND_URL=.*|PUBLIC_FRONTEND_URL=$url|" "$ENV_FILE"
    sed -i "s|https://[a-z0-9-]*\.trycloudflare\.com|$url|g" "$ENV_FILE"
    echo "  3) .env обновлён (PUBLIC_* и trycloudflare в CORS). Перезапустите run-local.sh"
  else
    echo "  3) Вручную в .env: PUBLIC_BASE_URL=$url и PUBLIC_FRONTEND_URL=$url"
  fi
  echo ""
}

# Без exec — парсим URL из лога cloudflared
"$CF" tunnel --url http://127.0.0.1:5173 2>&1 | while IFS= read -r line; do
  printf '%s\n' "$line"
  if [[ "$line" =~ https://[a-z0-9-]+\.trycloudflare\.com ]]; then
    u=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' <<<"$line" | head -1)
    save_url "$u"
  fi
done
