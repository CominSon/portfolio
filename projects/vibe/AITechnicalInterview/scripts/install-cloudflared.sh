#!/usr/bin/env bash
# Установка cloudflared в ~/.local/bin (без sudo)
set -euo pipefail

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64) ASSET="cloudflared-linux-amd64" ;;
  aarch64|arm64) ASSET="cloudflared-linux-arm64" ;;
  *)
    echo "Архитектура $ARCH: скачайте вручную с https://github.com/cloudflare/cloudflared/releases"
    exit 1
    ;;
esac

BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"
URL="https://github.com/cloudflare/cloudflared/releases/latest/download/${ASSET}"

echo "Скачиваю $URL ..."
curl -fsSL "$URL" -o "${BIN_DIR}/cloudflared"
chmod +x "${BIN_DIR}/cloudflared"
"${BIN_DIR}/cloudflared" --version

if ! echo ":${PATH}:" | grep -q ":${BIN_DIR}:"; then
  echo ""
  echo "Добавьте в ~/.bashrc (один раз):"
  echo '  export PATH="$HOME/.local/bin:$PATH"'
  echo "Затем: source ~/.bashrc   или откройте новый терминал"
fi

echo ""
echo "Готово. Дальше: cloudflared tunnel login"
echo "Документация: docs/DOMAIN_TUNNEL_RU_REG.md"
