# Podman в корпоративной сети (Сбер)

## Почему появляется `? Please select an image`

Два разных случая:

| Что в списке | Причина | Решение |
|--------------|---------|---------|
| `python:3.12-slim`, `node:20-alpine` | Базовые образы при **сборке** | Полные имена в `.env`: `PYTHON_IMAGE`, `NODE_IMAGE`, `POSTGRES_IMAGE` |
| `aitechnicalinterview_backend:latest` | Локально собранный образ при **запуске** | В `docker-compose.yml` уже стоит `image: localhost/ai-interview-backend:latest` |

**Решение для базовых образов:** в `.env` указать **полные** имена (с registry в начале).

**Решение для `aitechnicalinterview_*`:** не выбирайте корпоративный registry — обновите проект и пересоберите (см. ниже). Podman должен использовать образ с префиксом `localhost/`.

---

## Что сделать сейчас (пошагово)

### 1. Остановить зависшую сборку

`Ctrl+C` в терминале, где висит `podman-compose up --build`.

### 2. Обновить `.env`

Откройте файл `.env` в корне проекта и **добавьте или замените** три строки (registry — тот, который у вас обычно работает; чаще всего первый в списке ниже):

```env
PYTHON_IMAGE=registry.sigma.sbrf.ru/python:3.12-slim
NODE_IMAGE=registry.sigma.sbrf.ru/node:20-alpine
POSTGRES_IMAGE=registry.sigma.sbrf.ru/postgres:16-alpine
```

Если `registry.sigma.sbrf.ru` не качает образы, замените префикс на один из:

| Registry | Строка в `.env` |
|----------|-----------------|
| registry.sigma.sbrf.ru | `registry.sigma.sbrf.ru/python:3.12-slim` |
| registry-ci.sigma.sbrf.ru | `registry-ci.sigma.sbrf.ru/python:3.12-slim` |
| stage.sberosc.sigma.sbrf.ru | `stage.sberosc.sigma.sbrf.ru/python:3.12-slim` |

Скопируйте тот же префикс для `NODE_IMAGE` и `POSTGRES_IMAGE`.

### 3. (Опционально) Если в меню вы уже знаете рабочий пункт

На экране `? Please select an image` можно было выбрать стрелками, например:

- **`registry.sigma.sbrf.ru/python:3.12-slim`** — Enter

Запомните этот registry и пропишите его в `.env`, как в шаге 2, чтобы в следующий раз меню не появлялось.

### 4. Проверить pull одного образа

```bash
podman pull registry.sigma.sbrf.ru/python:3.12-slim
```

Если ошибка «manifest unknown» — смените тег на `3.11-slim` или другой registry из таблицы выше.

### 5. Удалить старые «короткие» теги (если спрашивает `aitechnicalinterview_backend`)

```bash
podman rmi aitechnicalinterview_backend:latest 2>/dev/null || true
podman rmi aitechnicalinterview_frontend:latest 2>/dev/null || true
```

### 6. Запустить снова

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
podman-compose up --build
```

После сборки образы должны называться `localhost/ai-interview-backend:latest` и `localhost/ai-interview-frontend:latest` — без вопроса про registry.

---

## Если python:3.12-slim нет в registry

В `.env`:

```env
PYTHON_IMAGE=registry.sigma.sbrf.ru/python:3.11-slim
```

Аналогично для `node` — можно попробовать `node:18-alpine`, если `20-alpine` нет.

---

## Если postgres:16-alpine нет

```env
POSTGRES_IMAGE=registry.sigma.sbrf.ru/postgres:15-alpine
```

или `postgres:16` без `-alpine`.

---

## Быстрая проверка после старта

| URL | Ожидание |
|-----|----------|
| http://localhost:5173 | Admin UI |
| http://localhost:8000/health | `{"status":"ok"}` |

---

## Всё ещё не работает

См. запуск **без контейнеров**: раздел «Альтернатива: запуск без Docker» в [ZAPUSK.md](ZAPUSK.md).
