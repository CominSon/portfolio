# Запуск локальной версии (пошагово)

Этот документ — **главная инструкция**. Следуйте шагам по порядку, чтобы увидеть Admin UI и комнату интервью в браузере.

---

## Что вы получите после запуска

| Адрес | Что это |
|-------|---------|
| http://localhost:5173 | **Admin UI** — настройка интервью (работодатель) |
| http://localhost:5173/interview/ТОКЕН | **Interview Room** — комната кандидата (ссылка из Admin) |
| http://localhost:8000/docs | Swagger API (для отладки) |
| http://localhost:8000/health | Проверка, что backend жив |

---

## Шаг 0. Что должно быть установлено

На машине нужен **Docker** или **Podman** (у вас может быть Podman с эмуляцией `docker`).

Проверка:

```bash
docker --version
docker compose version
```

Если `docker compose` не работает, попробуйте:

```bash
docker-compose --version
```

**Node.js на хосте не обязателен** — frontend собирается внутри контейнера.

---

## Шаг 1. Перейти в папку проекта

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
```

(Подставьте свой путь, если проект лежит в другом месте.)

---

## Шаг 2. Создать файл `.env`

```bash
cp .env.example .env
```

Откройте `.env` в редакторе. Для **первого просмотра UI** достаточно оставить значения по умолчанию.

### Что куда подставить

| Переменная | Куда взять значение | Обязательно для UI? |
|------------|---------------------|---------------------|
| `DEEPSEEK_API_KEY` | Ключ с https://platform.deepseek.com | **Нет**. Без ключа AI работает в **mock-режиме** (заглушка ответов). |
| `DEEPSEEK_BASE_URL` | Оставить `https://api.deepseek.com` | Нет |
| `DATABASE_URL` | Не менять при запуске через Docker | Нет (в compose уже задано для контейнера) |
| `RECORDINGS_DIR` | `./recordings` | Нет |
| `CORS_ORIGINS` | `http://localhost:5173` | Нет |

**Пример `.env` для первого запуска (только UI + mock AI):**

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DATABASE_URL=postgresql+asyncpg://interview:interview@localhost:5432/ai_interview
RECORDINGS_DIR=./recordings
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

---

## Шаг 3. Запустить все сервисы

Из корня проекта:

```bash
docker compose up --build
```

Или через скрипт:

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

Первый запуск **5–15 минут**: скачиваются образы, ставятся Python-зависимости (в т.ч. whisper), `npm install` для frontend.

Дождитесь в логах строк вроде:

- `postgres` — `database system is ready`
- `backend` — `Uvicorn running on http://0.0.0.0:8000`
- `frontend` — `Local: http://localhost:5173/`

Запуск в фоне:

```bash
docker compose up --build -d
docker compose logs -f frontend
```

Остановка:

```bash
docker compose down
```

---

## Шаг 4. Открыть Admin UI в браузере

1. Откройте **http://localhost:5173**
2. Должна открыться страница **«AI Technical Interview Platform»** с шагами 1–5.

Если страница не открывается — см. раздел «Проблемы» внизу.

---

## Шаг 5. Пройти минимальный сценарий (без реального AI)

### 5.1 Работодатель

- **Название компании:** любое, например `Тест Компания`
- **Email:** любой, например `hr@test.local`
- Нажмите **«Продолжить»**

### 5.2 Документы (можно пропустить файлы)

- **Email кандидата:** `candidate@test.local`
- Файлы вакансии/резюме — **необязательны** для просмотра UI; если не загружать, компетенции будут пустыми или из mock.
- Нажмите **«Загрузить и проанализировать»**

> Если backend ещё не поднялся, будет ошибка сети — подождите 1–2 минуты и повторите.

### 5.3 Компетенции

- Отредактируйте таблицу или нажмите **«Подтвердить»**

### 5.4 Формат интервью

- Режим **«AI выбирает автоматически»** → **«Сохранить формат»**

### 5.5 Ссылка для кандидата

- **«Сгенерировать ссылку»**
- Откройте ссылку в **новой вкладке** (или инкогнито) — это **Interview Room**

---

## Шаг 6. Interview Room (первичный просмотр)

На странице комнаты вы увидите:

- панель **Media validation** (камера / микрофон / экран);
- превью камеры (после разрешений браузера);
- **Monaco Editor**;
- чат **AI Interviewer**;
- кнопки **«Ответить»** и **«Отправить код»**.

Для полного сценария браузер запросит доступ к камере, микрофону и **демонстрации экрана** — без этого кнопка **«Начать интервью»** останется неактивной (это по ТЗ).

---

## Порты (если заняты)

| Сервис | Порт по умолчанию | Где менять |
|--------|-------------------|------------|
| Frontend | 5173 | `docker-compose.yml` → `frontend.ports` |
| Backend | 8000 | `docker-compose.yml` → `backend.ports` |
| PostgreSQL | 5432 | `docker-compose.yml` → `postgres.ports` |

После смены порта frontend обновите `CORS_ORIGINS` и `VITE_API_URL` в `docker-compose.yml`.

---

## Альтернатива: запуск без Docker (если образы не качаются)

На корпоративных машинах Podman может **не достучаться до registry** (ошибки `sigma.sbrf.ru`). Тогда поднимайте сервисы вручную.

### A. Только UI (быстрый просмотр вёрстки)

Нужны **Node.js 18+** и npm:

```bash
# Ubuntu/Debian (пример)
sudo apt update && sudo apt install -y nodejs npm

cd frontend
npm install
export VITE_API_URL=http://localhost:8000
export VITE_WS_URL=ws://localhost:8000
npm run dev
```

Откройте http://localhost:5173 — Admin откроется; шаги с API дадут ошибку, пока не запущен backend.

### B. UI + backend (полный локальный сценарий)

**Терминал 1 — PostgreSQL** (или `docker run -p 5432:5432 -e POSTGRES_USER=interview -e POSTGRES_PASSWORD=interview -e POSTGRES_DB=ai_interview postgres:16-alpine` если есть доступ к docker.io)

**Терминал 2 — backend** (Python 3.11+ рекомендуется):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+asyncpg://interview:interview@localhost:5432/ai_interview
export CORS_ORIGINS=http://localhost:5173
uvicorn app.main:app --reload --port 8000
```

**Терминал 3 — frontend** (см. блок A)

Проверка backend: http://localhost:8000/health

---

## Проблемы

### Зависание на `? Please select an image` (Podman / Сбер)

Podman ждёт, что вы **выберете registry стрелками и Enter**.

**Чтобы больше не спрашивало:** добавьте в `.env` полные имена образов (см. `.env.example`) и перезапустите сборку.

**Подробно:** [docs/PODMAN_SBER.md](PODMAN_SBER.md)

### Ошибки pull образов (Podman / корпоративный registry)

Симптом: `lookup ... sigma.sbrf.ru: no such host` или `manifest unknown`.

**Решение:** смените префикс в `PYTHON_IMAGE` / `NODE_IMAGE` / `POSTGRES_IMAGE` на другой registry из [PODMAN_SBER.md](PODMAN_SBER.md), либо запуск без Docker — раздел ниже.

### «docker: команда не найдена»

Установите Docker Desktop / Docker Engine или используйте Podman с `podman-compose`.

### Frontend не открывается на 5173

```bash
docker compose ps
docker compose logs frontend
```

Убедитесь, что контейнер `frontend` в статусе `running`.

### Ошибки API в Admin (Failed to fetch)

1. Проверьте backend: http://localhost:8000/health → `{"status":"ok"}`
2. Логи: `docker compose logs backend`

### Backend падает на faster-whisper

Первый запуск тяжёлый. Подождите или временно закомментируйте whisper в `requirements.txt` (для **только UI** можно поднять только frontend — см. ниже).

### Только UI без backend (ограниченный просмотр)

Если нужен **только внешний вид** без API:

```bash
cd frontend
docker build -t ai-interview-ui .
docker run --rm -p 5173:5173 -e VITE_API_URL=http://localhost:8000 ai-interview-ui
```

Страница откроется, но шаги Admin без backend будут с ошибками. **Рекомендуется полный `docker compose up`.**

### Podman вместо Docker

На системах с Podman (без `docker compose`) используйте:

```bash
podman-compose up --build
```

Или скрипт `./scripts/start.sh` — он подберёт команду автоматически.

---

## Следующие шаги

- Подключить реальный AI: задать `DEEPSEEK_API_KEY` в `.env` и перезапустить: `docker compose up --build`
- Остальная документация: [README.md](../README.md), [ARCHITECTURE.md](ARCHITECTURE.md)
