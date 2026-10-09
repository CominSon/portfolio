# Развёртывание

## Локальный MVP

### Требования
- Docker или Podman + Compose
- Ключ DeepSeek (опционально; без ключа — mock AI)

### Запуск

См. **[ZAPUSK.md](ZAPUSK.md)** — пошаговая инструкция.

```bash
cp .env.example .env
docker compose up --build
```

| Сервис | URL |
|--------|-----|
| Frontend | http://localhost:5173 |
| Backend | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| PostgreSQL | localhost:5432 |

### Без Docker (ручной запуск)

**Backend** (нужны Python 3.11+ и PostgreSQL):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Поднять PostgreSQL, прописать DATABASE_URL в .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

**Frontend** (нужны Node.js 20+):

```bash
cd frontend
npm install
export VITE_API_URL=http://localhost:8000
export VITE_WS_URL=ws://localhost:8000
npm run dev
```

---

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | URL async SQLAlchemy |
| `DEEPSEEK_API_KEY` | Ключ LLM |
| `DEEPSEEK_BASE_URL` | Базовый URL API |
| `RECORDINGS_DIR` | Папка записей |
| `CORS_ORIGINS` | Origins через запятую |

---

## VPS (будущее)

1. **Один VPS (4–8 GB RAM):** docker-compose + Caddy (TLS), тома для PG и записей.
2. **Записи:** MinIO/S3 вместо локальной папки.
3. **Whisper:** отдельный GPU-сервер для STT (опционально).
4. **Масштаб:** несколько реплик API + Redis pub/sub для WebSocket; managed PostgreSQL.
5. **Kubernetes** — только при высокой нагрузке; для MVP достаточно compose/systemd.

### Схема на VPS

```
Интернет → Caddy (TLS) → статика frontend + прокси /api, /ws → FastAPI
                      → PostgreSQL
                      → S3 для записей
```

Бэкапы: ежедневный дамп PG + репликация bucket записей.
