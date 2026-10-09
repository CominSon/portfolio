# AI Technical Interview Platform

Платформа для **автономных** технических интервью с AI-интервьюером (не чат-бот): голос, Monaco-редактор, своя interview room, отчёты работодателю.

---

## Быстрый старт (локально)

> **Registry недоступен (`no such host`)?** → **[docs/ZAPUSK_BEZ_KONTEINEROV.md](docs/ZAPUSK_BEZ_KONTEINEROV.md)**  
> `./scripts/run-local.sh`

> **С Docker/Podman:** [docs/ZAPUSK.md](docs/ZAPUSK.md)

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
cp .env.example .env
docker compose up --build
```

Откройте в браузере: **http://localhost:5173**

| Сервис | URL |
|--------|-----|
| Admin UI | http://localhost:5173 |
| API (Swagger) | http://localhost:8000/docs |

`DEEPSEEK_API_KEY` в `.env` **не обязателен** для первого просмотра — AI отвечает заглушками (mock).

---

## Возможности MVP

- **Admin UI** — вакансия/резюме (PDF, DOCX), компетенции, формат интервью, ссылка кандидату
- **Interview Room** — камера, микрофон, экран (обязательны), Monaco, чат AI, «Ответить» / «Отправить код»
- **AI** — DeepSeek (или mock без ключа), TTS (edge-tts), STT (faster-whisper)
- **Редактор** — синхронизация кода по WebSocket, timeline изменений
- **Запись** — чанки MediaRecorder на сервер

---

## Документация (на русском)

| Документ | Содержание |
|----------|------------|
| [docs/ZAPUSK.md](docs/ZAPUSK.md) | **Запуск, .env, сценарий в браузере** |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Архитектура системы |
| [docs/API_CONTRACTS.md](docs/API_CONTRACTS.md) | REST API |
| [docs/WEBSOCKET_CONTRACTS.md](docs/WEBSOCKET_CONTRACTS.md) | WebSocket-события |
| [docs/SCHEMA.sql](docs/SCHEMA.sql) | Схема PostgreSQL |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Локально и VPS |
| [docs/TECHNICAL_EMAIL.md](docs/TECHNICAL_EMAIL.md) | **Технический ящик для SMTP-рассылки** |
| [docs/MVP_PLAN.md](docs/MVP_PLAN.md) | План развития MVP |
| [docs/FOLDER_STRUCTURE.md](docs/FOLDER_STRUCTURE.md) | Структура папок |

---

## Стек

- Backend: Python, FastAPI, WebSocket, PostgreSQL  
- Frontend: React, TypeScript, Monaco Editor  
- AI: DeepSeek API  
- Голос: faster-whisper, edge-tts  

---

## Структура проекта

```
backend/app/     — API, сервисы, WebSocket
frontend/src/    — Admin + Interview Room
docs/            — документация
```

Лицензия: внутреннее использование.
