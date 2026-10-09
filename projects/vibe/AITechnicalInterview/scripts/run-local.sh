#!/usr/bin/env bash
# Локальный запуск БЕЗ Podman/Docker (когда registry.sigma недоступен)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() { echo -e "${GREEN}>>>${NC} $*"; }
warn() { echo -e "${YELLOW}!!!${NC} $*"; }
err()  { echo -e "${RED}!!!${NC} $*" >&2; }

# --- Python (pyenv + .python-version → 3.12.7) ---
if command -v pyenv >/dev/null && [[ -f "$ROOT/.python-version" ]]; then
  eval "$(pyenv init -)"
  WANT_PY=$(cat "$ROOT/.python-version")
  if ! pyenv versions --bare | grep -qx "$WANT_PY"; then
    info "Устанавливаю Python $WANT_PY через pyenv (один раз, ~2–5 мин) ..."
    pyenv install "$WANT_PY"
  fi
  pyenv local "$WANT_PY"
fi

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null; then
  err "Нужен python3. Рекомендуется: pyenv install 3.12.7 && pyenv local 3.12.7"
  exit 1
fi

PY_MM=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
info "Python $PY_MM ($("$PYTHON" -c 'import sys; print(sys.executable)'))"

if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  :
else
  err "Нужен Python 3.10 или новее."
  exit 1
fi

if "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info < (3, 14) else 1)'; then
  :
else
  err "Python 3.14 пока НЕ поддерживается (падают pydantic, asyncpg)."
  err "Переключитесь на 3.12:"
  err "  pyenv install 3.12.7"
  err "  cd \"$ROOT\" && pyenv local 3.12.7"
  err "  rm -rf backend/.venv"
  err "  ./scripts/run-local.sh"
  exit 1
fi

# --- Backend venv (пересоздать, если был собран на другой версии Python) ---
RECREATE_VENV=0
if [[ -d backend/.venv ]]; then
  VENV_PY=$(backend/.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "?")
  if [[ "$VENV_PY" != "$PY_MM" ]]; then
    warn "Старый venv на Python $VENV_PY — пересоздаю под $PY_MM ..."
    RECREATE_VENV=1
  fi
else
  RECREATE_VENV=1
fi

if [[ "$RECREATE_VENV" -eq 1 ]]; then
  rm -rf backend/.venv
  info "Создаю venv в backend/.venv ..."
  "$PYTHON" -m venv backend/.venv
fi

# shellcheck disable=SC1091
source backend/.venv/bin/activate

info "Устанавливаю зависимости backend ..."
pip install -q -U pip
info "PyTorch (CPU) для Silero TTS — без Microsoft/Bing ..."
pip install -q torch --index-url https://download.pytorch.org/whl/cpu
pip install -q -r backend/requirements-local.txt

mkdir -p "$ROOT/data" "$ROOT/recordings"

export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///${ROOT}/data/interview.db}"
export RECORDINGS_DIR="${RECORDINGS_DIR:-${ROOT}/recordings}"

# IP в локальной сети — чтобы открыть UI/API с других ПК в той же Wi‑Fi/LAN
LAN_IP="${LAN_IP:-}"
if [[ -z "$LAN_IP" ]]; then
  LAN_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
  if [[ -z "$LAN_IP" ]] && command -v ip >/dev/null; then
    LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
  fi
fi

DEFAULT_CORS="http://localhost:5173,http://127.0.0.1:5173"
if [[ -n "$LAN_IP" ]]; then
  DEFAULT_CORS="${DEFAULT_CORS},http://${LAN_IP}:5173"
fi
export CORS_ORIGINS="${CORS_ORIGINS:-$DEFAULT_CORS}"

info "Backend: $DATABASE_URL"

free_port() {
  local port=$1
  if ! command -v lsof >/dev/null 2>&1; then
    return 0
  fi
  local pids
  pids=$(lsof -ti :"$port" 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    warn "Порт $port занят (pid: $pids) — останавливаю предыдущий процесс..."
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 1
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
}

free_port 8000
free_port 5173

info "Запуск API на http://localhost:8000 ..."

cd "$ROOT/backend"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd "$ROOT"

cleanup() {
  info "Остановка backend (pid $BACKEND_PID) ..."
  kill "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

info "Ожидаю готовности backend (до 60 с, reloader uvicorn стартует не сразу) ..."
HEALTH_OK=0
for _ in $(seq 1 60); do
  if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    HEALTH_OK=1
    break
  fi
  sleep 1
done
if [[ "$HEALTH_OK" -ne 1 ]]; then
  err "Backend не ответил на /health за 60 с — смотрите логи выше"
  wait "$BACKEND_PID" || true
  exit 1
fi
info "Backend OK: http://localhost:8000/health"

# --- Frontend ---
if ! command -v npm >/dev/null; then
  err "Node.js/npm не найден. Установите Node 18+ или откройте только API: http://localhost:8000/docs"
  err "Backend продолжит работать, пока не закроете этот терминал (Ctrl+C)."
  wait "$BACKEND_PID"
  exit 1
fi

info "Устанавливаю зависимости frontend ..."
cd "$ROOT/frontend"
npm install --silent 2>/dev/null || npm install

# API через прокси Vite (/api, /ws) — не задаём VITE_API_URL, чтобы не ловить CORS
unset VITE_API_URL VITE_WS_URL

info "Frontend: http://localhost:5173  (открывайте именно localhost, не 127.0.0.1)"
if [[ -n "$LAN_IP" ]]; then
  echo ""
  info "Доступ с других машин в той же сети:"
  echo "       UI:    http://${LAN_IP}:5173"
  echo "       API:   http://${LAN_IP}:8000/docs"
  echo "  В .env для ссылок в письмах и кандидату:"
  echo "       PUBLIC_BASE_URL=http://${LAN_IP}:8000"
  echo "  (ссылка на интервью: http://${LAN_IP}:5173/interview/ТОКЕН)"
  warn "Камера/экран с чужого ПК по HTTP могут не работать — см. docs/DOSTUP_V_LAN.md"
  echo ""
fi
info "Нажмите Ctrl+C для остановки."
npm run dev -- --host 0.0.0.0
