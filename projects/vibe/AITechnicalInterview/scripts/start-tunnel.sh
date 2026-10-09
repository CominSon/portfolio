#!/usr/bin/env bash
# Проброс локального UI (5173) в интернет через Cloudflare Tunnel.
# Сначала: ./scripts/run-local.sh в другом терминале.
# Настройка: docs/NASTRAIVAEM_interviewaimvp.ru.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CFG="${CLOUDFLARED_CONFIG:-$HOME/.cloudflared/config.yml}"

# Токен из .env (способ для .ru без домена в Cloudflare)
if [[ -f "$ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  set -a
  source <(grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' "$ROOT/.env" | sed 's/\r$//') 2>/dev/null || true
  set +a
fi

export PATH="${HOME}/.local/bin:${PATH}"

find_cloudflared() {
  if command -v cloudflared >/dev/null 2>&1; then
    command -v cloudflared
    return 0
  fi
  if [[ -x "${HOME}/.local/bin/cloudflared" ]]; then
    echo "${HOME}/.local/bin/cloudflared"
    return 0
  fi
  return 1
}

CF="$(find_cloudflared || true)"
if [[ -z "$CF" ]]; then
  echo "cloudflared не найден. Запустите: ./scripts/install-cloudflared.sh"
  exit 1
fi

echo "cloudflared: $CF"
echo "Убедитесь, что ./scripts/run-local.sh уже запущен."

if [[ -n "${CLOUDFLARE_TUNNEL_TOKEN:-}" ]]; then
  echo "Туннель по токену (Zero Trust) → http://127.0.0.1:5173"
  exec "$CF" tunnel run --token "$CLOUDFLARE_TUNNEL_TOKEN"
fi

if [[ ! -f "$CFG" ]]; then
  echo "Нет CLOUDFLARE_TUNNEL_TOKEN в .env и нет $CFG"
  echo "Инструкция: $ROOT/docs/NASTRAIVAEM_interviewaimvp.ru.md"
  exit 1
fi

echo "Туннель по config.yml → http://127.0.0.1:5173"
exec "$CF" tunnel --config "$CFG" run
