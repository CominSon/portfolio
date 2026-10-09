# Yandex SpeechKit STT — пошаговая настройка

Цель: получить `YANDEX_FOLDER_ID` и `YANDEX_API_KEY`, проверить распознавание тестовым скриптом, потом включить в проекте `STT_PROVIDER=yandex`.

Официальные материалы:
- [Quickstart STT v2 (AI Studio)](https://aistudio.yandex.ru/docs/ru/speechkit/quickstart/stt-quickstart-v2.html)
- [Синхронное распознавание (короткие файлы)](https://yandex.cloud/ru/docs/speechkit/quickstart/stt-quickstart-v1)
- [Тарифы SpeechKit](https://yandex.cloud/ru/docs/speechkit/pricing)

---

## Шаг 1. Куда идти

1. Откройте **[console.cloud.yandex.ru](https://console.cloud.yandex.ru/)** (нужен аккаунт Яндекса).
2. Если облака ещё нет — создайте **облако** (Cloud) с любым именем.
3. Внутри облака создайте **каталог** (Folder), например `ai-interview-dev`.
4. Запомните **ID каталога** — строка вида `b1gxxxxxxxxxxxxxxxx`.
   - Консоль → выберите каталог → в URL или в «Свойствах» будет `folderId`.

Альтернатива: [AI Studio](https://aistudio.yandex.ru/) — тот же Yandex Cloud, те же ключи и каталоги.

---

## Шаг 2. Что и где оплачивать

SpeechKit — **платный облачный сервис** (оплата за распознанные секунды аудио).

1. В консоли: **Биллинг** → привяжите **платёжный аккаунт** (карта).
2. У новых аккаунтов часто есть **стартовый грант** (проверьте в разделе «Биллинг» / «Промо»).
3. Тарифы смотрите в [документации по ценам SpeechKit](https://yandex.cloud/ru/docs/speechkit/pricing) — обычно копейки за секунду распознавания; для тестов уйдёт несколько рублей.

Без привязанного биллинга API вернёт ошибку доступа.

---

## Шаг 3. Сервисный аккаунт и API-ключ

1. Консоль → ваш **каталог** → **Сервисные аккаунты** → **Создать**.
   - Имя, например: `speechkit-stt`.
2. **Важно — роль назначается сервисному аккаунту на каталог**, а не вашему логину.

   Частая ошибка: открыть сервисный аккаунт → вкладка **«Права доступа»** и увидеть там себя с ролью `ai.speechkit-stt.user`. Это **не то** — там перечислены люди, которые управляют самим аккаунтом.

   Правильный путь:
   - Вернитесь в **каталог** `default` (клик по имени каталога в шапке, не внутри карточки SA).
   - Слева: **Права доступа** (к каталогу).
   - **Назначить роли** → субъект: **сервисный аккаунт** `speechkit-stt` / `maxai`.
   - Роль: **`ai.speechkit-stt.user`**.
   - Сохранить.

   В списке прав каталога должна появиться строка: `maxai` (сервисный аккаунт) → `ai.speechkit-stt.user`.

3. Снова откройте сервисный аккаунт → вкладка **API-ключи** → **Создать API-ключ** → скопируйте значение **сразу** (показывается один раз).
   - Область действия (scope): **`yc.ai.speechkitStt.execute`**.
   - Выглядит как `AQVN...`.

IAM-токен тоже подходит, но для сервера проще **API-ключ** — не протухает каждые 12 часов.

---

## Шаг 4. Куда вписать в проекте

В корне репозитория файл **`.env`** (скопируйте из `.env.example`, если ещё нет):

```env
# --- Yandex SpeechKit STT ---
YANDEX_FOLDER_ID=b1gxxxxxxxxxxxxxxxx
YANDEX_API_KEY=AQVNxxxxxxxxxxxxxxxx
YANDEX_STT_LANG=ru-RU
# YANDEX_STT_TOPIC=general
```

| Переменная | Где взять |
|------------|-----------|
| `YANDEX_FOLDER_ID` | Консоль → Каталог → ID |
| `YANDEX_API_KEY` | Сервисный аккаунт → API-ключи |
| `YANDEX_STT_LANG` | `ru-RU` для русского |

**Не коммитьте** `.env` в git (секреты).

После успешного теста в приложении будет:

```env
STT_PROVIDER=yandex
```

(интеграция в backend — отдельным шагом после теста).

---

## Шаг 5. Тестовый скрипт (сначала он)

### 5.1. Подготовьте короткий аудиофайл (5–20 секунд)

Любой из вариантов:

- Запишите голос на телефон → экспорт **.ogg** или **.wav**
- Или возьмите файл из записи интервью: `recordings/.../answer.webm` (скрипт сконвертирует через `ffmpeg`, если установлен)

Синхронный API v1 рассчитан на **короткие** фрагменты (порядка до ~30 с). Для длинных ответов позже подключим **async v2** + Object Storage.

### 5.2. Запуск

```bash
cd /path/to/AITechnicalInterview

# 1) Только проверка ключей (без речи)
backend/.venv/bin/python scripts/test_yandex_stt.py --check-auth

# 2) Нормальный тест — последняя запись интервью (рекомендуется)
backend/.venv/bin/python scripts/test_yandex_stt.py --sample

# 3) Конкретный файл
backend/.venv/bin/python scripts/test_yandex_stt.py recordings/<id>/audio/recording.webm --seconds 25
```

### 5.3. Успех

В конце увидите:

```
--- Распознанный текст ---
<ваш текст>

OK: Yandex STT отвечает, ключи и каталог настроены верно.
```

### 5.4. Типичные ошибки

| Сообщение | Что сделать |
|-----------|-------------|
| `401` + `Permission denied` | Роль `ai.speechkit-stt.user` должна быть у **сервисного аккаунта** на **каталоге** (не у вашего логина на странице SA). Scope ключа: `yc.ai.speechkitStt.execute`. Проверьте биллинг |
| `401` + `InvalidArgument` + `folder ID` | Неверный `YANDEX_FOLDER_ID` |
| `401` / `Unauthorized` (другое) | Проверьте `YANDEX_API_KEY`, создайте новый ключ |
| Пустой `result` | Говорите громче, файл > 1 с, формат ogg/wav |
| Биллинг | Привяжите платёжный аккаунт в консоли |

---

## TTS (озвучка AI-интервьюера)

Те же `YANDEX_FOLDER_ID` и `YANDEX_API_KEY`, но нужны **отдельные права на синтез**:

1. Каталог → **Права доступа** → сервисному аккаунту добавьте роль **`ai.speechkit-tts.user`** (в дополнение к STT).
2. API-ключ: scope **`yc.ai.speechkitTts.execute`** (можно создать второй ключ или ключ с обоими scope, если консоль позволяет).
3. В `.env`:

```env
TTS_ENGINE=yandex
YANDEX_TTS_VOICE=alena
YANDEX_TTS_SPEED=0.95
YANDEX_TTS_EMOTION=good
```

**Приятные голоса (ru-RU):**

| Голос | Описание |
|-------|----------|
| `alena` | Спокойный женский, хорош для интервью (по умолчанию) |
| `marina` | Мягкий женский |
| `jane` | Нейтральный женский |
| `alena:premium` | Премиум-качество (если доступно в тарифе) |
| `filipp` | Мужской |

Тариф: порядка **0,16 ₽ за 1000 символов** — на одно интервью обычно копейки.

Проверка:

```bash
cd backend && source .venv/bin/activate
python -c "
from pathlib import Path
from app.config import get_settings
from app.services.tts_yandex import synthesize_yandex_mp3
s = get_settings()
p = Path('../recordings/tts/test-yandex.mp3')
ok = synthesize_yandex_mp3('Здравствуйте! Я Айри, ваш AI-интервьюер. Начнём техническое собеседование.', p, s)
print('ok=', ok, 'path=', p)
"
```

Перезапустите backend после смены `.env`.

---

## Шаг 6. Что дальше (после успешного теста)

1. Встроить провайдер `yandex` в `backend/app/services/voice_pipeline.py`.
2. Для ответов **дольше 30 с** — async API v2 (`longRunningRecognize`) и при необходимости бакет Object Storage.
3. В `.env` выставить `STT_PROVIDER=yandex` и перезапустить backend.

---

## Краткая шпаргалка

```
console.cloud.yandex.ru
  → Каталог (folder_id)
  → Биллинг (карта)
  → Сервисный аккаунт + роль ai.speechkit-stt.user
  → API-ключ → .env (YANDEX_FOLDER_ID, YANDEX_API_KEY)
  → python scripts/test_yandex_stt.py sample.ogg
```
