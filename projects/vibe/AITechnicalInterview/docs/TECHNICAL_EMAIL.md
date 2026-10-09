# Почта Mail.ru для рассылки отчётов

## 1. Включить доступ по SMTP

1. [Почта Mail.ru](https://e.mail.ru/settings) → **Все настройки** → **Почтовые программы**.
2. Включите **Доступ по IMAP, POP и SMTP**.

## 2. Пароль для внешнего приложения

Обычный пароль от ящика **не подойдёт** (ошибка `535 Application password is REQUIRED`).

Если видите эту ошибку — вы вписали пароль входа в Mail.ru, а нужен **отдельный** пароль из шага ниже.

1. [id.mail.ru](https://id.mail.ru/) → **Безопасность** → **Пароли для внешних приложений**.
2. Создайте пароль (название, например `AI Interview`).
3. Скопируйте в `.env` → `SMTP_PASSWORD=...`

## 3. `.env`

```env
SMTP_HOST=smtp.mail.ru
SMTP_PORT=465
SMTP_USE_TLS=false
SMTP_USE_SSL=true
SMTP_USER=icemaakkss@mail.ru
SMTP_PASSWORD=пароль_из_шага_2
EMAIL_FROM=icemaakkss@mail.ru
EMAIL_FROM_NAME=AI Technical Interview
PUBLIC_BASE_URL=http://localhost:8000
```

Альтернатива: порт **587**, `SMTP_USE_TLS=true`, `SMTP_USE_SSL=false`.

## 4. Проверка

```bash
backend/.venv/bin/python scripts/test_smtp.py you@example.com
```

## Без пароля

Отчёт сохраняется в БД; письмо не уходит, текст в логе backend.

## Письма работодателю (два письма)

После интервью отправляются **два письма**:

1. **Отчёт** — сразу после завершения, с крупной припиской, что видео придёт отдельно примерно через 2 часа (`MONTAGE_EMAIL_DELAY_HOURS` в `.env`).
2. **Видео** — когда собран `montage.mp4` (экран слева, камера справа, звук с микрофона).

Сборка MP4 на CPU может занимать от десятков минут до нескольких часов для длинных интервью — отчёт не ждёт монтаж.

Ссылка на видео: `/api/v1/interviews/{id}/recordings/montage`

Пересборка и повторная отправка:

```bash
# отчёт + пересборка видео + письмо с видео
backend/.venv/bin/python scripts/resend_report_email.py you@example.com

# только отчёт
backend/.venv/bin/python scripts/resend_report_email.py you@example.com --report-only

# только видео (если montage уже есть: --skip-rebuild)
backend/.venv/bin/python scripts/resend_report_email.py you@example.com --video-only
```
