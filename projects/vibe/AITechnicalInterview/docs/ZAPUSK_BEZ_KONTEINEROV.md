# Запуск без Podman/Docker (когда registry недоступен)

## Ваша ошибка

```
lookup registry.sigma.sbrf.ru: no such host
```

С этой машины **корпоративный registry не резолвится** (нет VPN / другая сеть).  
Podman **не сможет** скачать `python`, `node`, `postgres` — контейнеры не поднимутся.

Ошибка `localhost/ai-interview-backend` — следствие: **сборка не прошла**, образа нет, Podman пытается его «скачать».

---

## Решение: локальный запуск (рекомендуется)

Нужны:
- **Python 3.10+** (проверка: `python3 --version`)
- Пакет **python3-venv** (Ubuntu: `sudo apt install python3-venv`)
- **Node.js 18+** и npm (проверка: `node -v`, `npm -v`)

### Одна команда

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
chmod +x scripts/run-local.sh
./scripts/run-local.sh
```

Скрипт:
1. Создаёт `backend/.venv`, ставит зависимости (без тяжёлого whisper)
2. Поднимает API на **http://localhost:8000** (БД SQLite в `data/interview.db`)
3. Ставит npm-пакеты и открывает UI на **http://localhost:5173**

Остановка: **Ctrl+C**.

### Доступ с других ПК в локальной сети

См. **[DOSTUP_V_LAN.md](DOSTUP_V_LAN.md)** — IP вместо localhost, `.env`, файрвол, ограничение камеры по HTTP.

### Вручную (два терминала)

**Терминал 1 — backend:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-local.txt
cd ..
export DATABASE_URL="sqlite+aiosqlite:///$(pwd)/data/interview.db"
mkdir -p data recordings
cd backend && uvicorn app.main:app --reload --port 8000
```

**Терминал 2 — frontend:**

```bash
cd frontend
npm install
export VITE_API_URL=http://localhost:8000
export VITE_WS_URL=ws://localhost:8000
npm run dev
```

---

## Что подставить в `.env`

Файл в **корне проекта**. Для локального запуска достаточно:

```env
DEEPSEEK_API_KEY=          # пусто = mock AI
DATABASE_URL=sqlite+aiosqlite:///./data/interview.db
CORS_ORIGINS=http://localhost:5173
```

Строки `PYTHON_IMAGE`, `NODE_IMAGE`, `POSTGRES_IMAGE` — **только для Podman**, при локальном запуске не нужны.

---

## Проверка

| URL | Ожидание |
|-----|----------|
| http://localhost:8000/health | `{"status":"ok"}` |
| http://localhost:5173 | Admin UI |

---

## Когда снова использовать Podman

1. Подключить VPN / сеть, где открывается `registry.sigma.sbrf.ru` (или другой registry).
2. Либо в `.env` указать **docker.io** (если разрешён интернет):

```env
PYTHON_IMAGE=docker.io/library/python:3.12-slim
NODE_IMAGE=docker.io/library/node:20-alpine
POSTGRES_IMAGE=docker.io/library/postgres:16-alpine
```

3. `podman-compose up --build`

---

## Нет Node.js

Установите Node 18+ (с сайта nodejs.org, nvm или через администратора).

Пока можно смотреть только API: http://localhost:8000/docs
