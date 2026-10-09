# Архитектура системы — AI Technical Interview Platform

## 1. Обзор

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        БРАУЗЕР (кандидат / работодатель)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐ │
│  │ Admin SPA    │  │ Interview    │  │ Monaco       │  │ Media: WebRTC +   │ │
│  │ (React)      │  │ Room         │  │ Editor       │  │ MediaRecorder     │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘ │
└─────────┼─────────────────┼─────────────────┼───────────────────┼───────────┘
          │ REST            │ WebSocket       │ код (WS)          │ чанки записи
          ▼                 ▼                 ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI (монолит MVP, один процесс)                       │
│  REST │ WS Hub │ InterviewSession │ EditorSync │ Recording │ DeepSeek       │
│  STT (whisper) │ TTS (edge-tts)                                              │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    ▼
                          ┌──────────────────┐
                          │   PostgreSQL     │
                          └──────────────────┘
```

**Принципы MVP:**
- Один backend, одна БД, без Kubernetes/Redis/microservices
- AI реагирует **только** после «Ответить» / «Отправить код»
- Редактор: последовательные операции по WebSocket (готовность к CRDT)
- Код **не исполняется** — только статический анализ через LLM

---

## 2. Backend (модульная OOP-архитектура)

| Модуль | Назначение |
|--------|------------|
| `InterviewSessionManager` | Жизненный цикл сессии интервью |
| `WebSocketManager` | Комнаты по `interview_id`, broadcast |
| `RecordingManager` | Метаданные и чанки записи с клиента |
| `TranscriptManager` | STT, спикеры, таймлайн |
| `DeepSeekOrchestrator` | Промпты, контекст, решения AI |
| `CompetencyAnalyzer` | Навыки из вакансии + резюме |
| `ScoringEngine` | Оценки по компетенциям |
| `ReportBuilder` | Итоговый отчёт работодателю |
| `CollaborativeEditorManager` | Фасад операций с кодом |
| `CodeOperationsManager` | insert/delete/replace/highlight/comment |
| `CodeTimelineManager` | Журнал событий редактора |
| `EditorSynchronizationManager` | seq, применение ops (задел под CRDT) |
| `DocumentParser` | PDF/DOCX/DOC → текст |
| `TextNormalizer` | Очистка и нормализация текста |
| `DocumentAnalysisManager` | LLM-анализ документов |
| `TemplateManager` | Шаблоны интервью |

---

## 3. Frontend

```
src/
├── features/admin/           # Работодатель
├── features/interview-room/  # Кандидат
├── editor/                   # Monaco
└── services/                 # api, websocket, media
```

**Комната интервью:** камера, media panel, Monaco, AI-чат, transcript, timeline, кнопки ответа.

---

## 4. Жизненный цикл интервью

```
CREATED → DOCUMENTS_UPLOADED → COMPETENCIES_CONFIRMED → FORMAT_SELECTED
→ SESSION_LINK_GENERATED → CANDIDATE_JOINED → MEDIA_PRECHECK → READY
→ ACTIVE ⇄ PAUSED → COMPLETING → REPORT_READY
```

**Media gate:** без камеры + микрофона + экрана интервью не стартует.  
**AI:** активен только в `ACTIVE` после submit кандидата.

---

## 5. Жизненный цикл AI

1. Загрузка контекста (компетенции, формат, время, код)
2. Submit кандидата → STT (если голос) → DeepSeek → текст в UI → TTS
3. При необходимости — code_actions по WebSocket
4. Адаптация сложности и смена компетенций по времени
5. Завершение → ScoringEngine → ReportBuilder

---

## 6. Запись

Клиент: MediaRecorder → чанки → `POST /recordings/chunk`.  
Сервер: файлы + метаданные, привязка transcript/editor events к `offset_ms`.

---

## 7. STT / TTS

- **TTS:** текст AI → edge-tts → MP3 → воспроизведение в браузере  
- **STT:** аудио с «Ответить» → faster-whisper → текст  

Порядок: **сначала текст в чате, затем голос**.

---

## 8. Совместное редактирование (MVP)

Сервер хранит авторитетный `editor_content` и `seq`.  
Клиенты шлют `code_insert|delete|replace` → broadcast `code_applied`.  
В будущем: CRDT/OT за интерфейсом `EditorSynchronizationManager`.

---

## 9. Документы и шаблоны

Upload → парсер → нормализация → LLM → предложенные компетенции.  
Шаблон хранит матрицу навыков, форматы, scoring, AI behavior — при новом кандидате только резюме.

---

## 10. VPS (будущее)

Compose + Caddy + TLS; записи в S3; опционально GPU для whisper.  
Горизонтальное масштабирование — после роста нагрузки, не для MVP.
