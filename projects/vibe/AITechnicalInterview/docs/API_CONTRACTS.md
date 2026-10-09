# Контракты REST API

Базовый URL: `http://localhost:8000/api/v1`

## Работодатели

### `POST /employers`
```json
{ "name": "Компания", "email": "hr@company.ru" }
```

### `GET /employers/{employer_id}`

## Шаблоны

### `POST /templates`
```json
{
  "employer_id": "uuid",
  "name": "Senior Backend",
  "duration_minutes": 60,
  "competencies": [
    { "skill": "Python", "level": "Senior", "weight": 40, "source": "manual" }
  ],
  "allowed_formats": ["Live Coding", "Code Review"],
  "format_selection_mode": "auto",
  "settings": {
    "ai_behavior": { "tone": "professional", "strictness": 0.7 },
    "scoring_rules": { "pass_threshold": 65 },
    "evaluation_priorities": ["code_quality", "communication"]
  }
}
```

### `GET /templates?employer_id=uuid`
### `GET /templates/{template_id}`

## Интервью

### `POST /interviews`
```json
{
  "employer_id": "uuid",
  "candidate_email": "dev@example.com",
  "template_id": "uuid (опционально)",
  "job_description_text": "опционально",
  "resume_text": "опционально"
}
```

### `POST /interviews/{id}/documents`
Multipart: `job_description`, `resume` (pdf, docx, doc)

### `POST /interviews/{id}/analyze-documents`
Запускает анализ → предложенные компетенции

### `PUT /interviews/{id}/competencies`
```json
{ "competencies": [{ "skill": "Python", "level": "Senior", "weight": 40, "source": "confirmed" }] }
```

### `PUT /interviews/{id}/format`
```json
{
  "format_selection_mode": "auto | restricted | manual",
  "allowed_formats": ["Live Coding"],
  "selected_format": "Live Coding"
}
```

### `POST /interviews/{id}/generate-link`
Возвращает `candidate_link` для кандидата

### `GET /interviews/join/{token}` — вход кандидата по токену

### `POST /interviews/{id}/media-status`
```json
{ "camera_enabled": true, "microphone_enabled": true, "screenshare_enabled": true }
```

### `POST /interviews/{id}/start` — старт (нужны все media)

### `POST /interviews/{id}/submit-answer`
```json
{ "answer_type": "voice | code", "text": "..." }
```

### `POST /interviews/{id}/stt` — файл audio/webm → `{ "text": "..." }`

### `GET /interviews/{id}/tts?text=...` — аудио MP3

### `POST /interviews/{id}/recordings/chunk` — чанк записи

### `POST /interviews/{id}/complete` — завершение и генерация отчёта

### `GET /interviews/{id}/report` — отчёт работодателю
