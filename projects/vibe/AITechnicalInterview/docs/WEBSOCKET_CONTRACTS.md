# Контракты WebSocket

**Подключение:** `WS /ws/interviews/{interview_id}?token={токен_кандидата}`

Сообщения — JSON.

## Подключение

```json
{
  "type": "connected",
  "interview_id": "uuid",
  "role": "candidate | employer",
  "editor_state": { "content": "", "language": "python", "version": 0, "seq": 0 }
}
```

## Редактор

| Тип | Направление | Описание |
|-----|-------------|----------|
| `code_insert` | клиент → сервер | Вставка текста |
| `code_delete` | клиент → сервер | Удаление по range |
| `code_replace` | клиент → сервер | Замена |
| `code_applied` | сервер → все | Op применён, есть `seq` |
| `cursor_move` | клиент → все | Курсор |
| `selection_change` | клиент → все | Выделение |
| `line_highlight` | AI → все | Подсветка строк |
| `inline_comment` | AI → все | Комментарий к строке |
| `ai_code_action` | сервер → все | Действие AI с кодом |
| `candidate_code_action` | сервер → все | Действие кандидата |

Пример `code_insert`:
```json
{
  "type": "code_insert",
  "range": { "startLine": 1, "startColumn": 1, "endLine": 1, "endColumn": 1 },
  "text": "def foo():\n    pass\n"
}
```

## Интервью и AI

| Тип | Описание |
|-----|----------|
| `interview_event` | `paused`, `started`, … |
| `transcript_update` | Новая реплика в транскрипте |
| `ai_message` | Текст AI в чат |
| `ai_voice_started` / `ai_voice_finished` | Озвучка |
| `ai_typing` | Индикатор набора |

## Media

`camera_enabled`, `camera_disabled`, `microphone_enabled`, `microphone_disabled`,  
`screenshare_started`, `screenshare_stopped`

При потере media во время интервью — `interview_event` с `event: "paused"`.

## Ошибки

```json
{ "type": "error", "code": "MEDIA_REQUIRED", "message": "..." }
```

## Синхронизация

Запрос `sync_state` → полный `editor_state` с сервера.
