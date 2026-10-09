# Portfolio

Подборка рабочих скриптов и сервисов для демонстрации работодателю.

## Структура

| Папка | Смысл |
|-------|--------|
| `projects/solo/` | Код, написанный вручную без AI |
| `projects/hybrid/` | AI + мой контроль и правки |
| `projects/vibe/` | Агент писал код при минимальном ревью |

## Solo

- **SpodUI** — автоматизация СПОД (Selenium, Excel, Greenplum)
- **FailCheck** — мониторинг FAILED по PXF/процедурам
- **SchedulePXF** — расписание загрузок PXF из Excel
- **SMDProxy** — PXF/PROXY-загрузки по Excel
- **Vacuum** — `VACUUM FULL ANALYZE` по схемам GP
- **connectBD** — библиотека подключений (GP / Hive / Oracle)

## Hybrid

- **AIDialogRadar** — RAG-поиск по группам СберЧата (GigaChat, FAISS, Flask)
- **AINavPDFAgent** — AI-агент PDF-выгрузок (GigaChat, почта, PG)
- **GolandProjects/gym_bot** — Telegram-бот записи на занятия (Go)

## Vibe

- **AITechnicalInterview** — full-stack AI-собеседования (FastAPI + React, STT/TTS, Docker)
- **AIWidgetSummaryOS** — агент отчётов по виджетам УБ
- **MCPServers** — набор MCP-агентов (GP, mail, Bitbucket, reports)

## Запуск

У каждого проекта свой README (где есть). Секреты и локальные `.env` в репозиторий не входят — используйте `.env.example`.
