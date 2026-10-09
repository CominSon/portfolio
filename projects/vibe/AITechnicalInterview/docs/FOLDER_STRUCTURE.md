# Структура папок проекта

```
AITechnicalInterview/
├── docker-compose.yml      # Локальный запуск: postgres + backend + frontend
├── .env.example            # Шаблон переменных (скопировать в .env)
├── README.md
├── scripts/
│   └── start.sh            # Скрипт быстрого запуска
├── docs/                   # Вся документация (русский)
│   ├── ZAPUSK.md           # ★ Главная инструкция по запуску
│   ├── ARCHITECTURE.md
│   ├── API_CONTRACTS.md
│   ├── WEBSOCKET_CONTRACTS.md
│   ├── SCHEMA.sql
│   ├── DEPLOYMENT.md
│   ├── MVP_PLAN.md
│   └── FOLDER_STRUCTURE.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic/            # Миграции БД
│   └── app/
│       ├── main.py         # Точка входа FastAPI
│       ├── config.py       # Настройки из .env
│       ├── database.py
│       ├── api/routes/     # REST: employers, templates, interviews
│       ├── models/         # Таблицы PostgreSQL
│       ├── schemas/        # Pydantic-модели запросов/ответов
│       ├── services/       # Бизнес-логика (менеджеры)
│       └── websocket/      # Обработчик WebSocket
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx, App.tsx
        ├── services/       # api.ts, websocket.ts, media.ts
        ├── editor/         # Monaco Editor
        └── features/
            ├── admin/      # Admin UI (работодатель)
            └── interview-room/  # Комната кандидата
```
