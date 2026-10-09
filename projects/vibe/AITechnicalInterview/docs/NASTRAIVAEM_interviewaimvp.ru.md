# interviewaimvp.ru — настройка с нуля (пошагово)

**Цель:** с любого интернета открывается **https://app.interviewaimvp.ru**, сервер крутится на вашем ПК.

---

## Если туннель Healthy, а сайт не открывается

### 1. Опечатка в Public Hostname

В Cloudflare должно быть **`app.interviewaimvp.ru`** (с **ai**).

Неверно: `app.interviewmvp.ru` — DNS в REG.RU на другой домен, сайт не совпадёт.

Исправление: туннель → **Routes / Public Hostname** → изменить на `app.interviewaimvp.ru`.

### 2. Служба должна быть HTTP, не HTTPS

Vite отдаёт **`http://localhost:5173`**, не https.

В Public Hostname:

| Поле | Верно | Неверно |
|------|-------|---------|
| URL | `http://127.0.0.1:5173` (предпочтительно) или `http://localhost:5173` |

В логах cloudflared при ошибке видно: `service=https://localhost:5173` — поменяйте на **http**.

После правки перезапустите `./scripts/start-tunnel.sh`.

---

Это **нормально**. Команда `tunnel login` просит домен **внутри** Cloudflare, а **interviewaimvp.ru** туда добавить нельзя (.ru).

**Не нажимайте** «добавьте сайт» для interviewaimvp.ru — не сработает.

Используйте **туннель через Zero Trust + токен** (ниже). DNS домена остаётся в **REG.RU**.

---

## ШАГ 1. cloudflared на ПК

```bash
cd "/home/my_profile/Документы/OthersProjects/AITechnicalInterview"
./scripts/install-cloudflared.sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
cloudflared --version
```

---

## ШАГ 2. Туннель в Cloudflare (без домена в списке)

1. Откройте: **https://one.dash.cloudflare.com/**
2. Первый раз: создайте бесплатную команду (любое имя, план Free).
3. Слева: **Networks** → **Connectors** → **Cloudflared** (или **Tunnels**).
4. **Create a tunnel** / **Создать туннель**.
5. Тип: **Cloudflared** → **Next**.
6. Имя туннеля: `ai-interview` → **Save tunnel**.
7. На шаге **Install connector** скопируйте **только токен** из команды:

   ```text
   cloudflared tunnel run --token eyJh......длинная_строка......
   ```

   Скопируйте всё после `--token ` (начинается с `eyJ`).

8. **Не закрывайте** страницу — нажмите **Next** до раздела **Public Hostname** (Публичный хост).

### Public Hostname (куда ведёт домен)

| Поле | Значение |
|------|----------|
| Subdomain | `app` |
| Domain | выберите из списка или введите **interviewaimvp.ru** если есть поле custom |
| Path | пусто |
| Type | HTTP |
| URL | `localhost:5173` |

Если в Domain нельзя выбрать interviewaimvp.ru — добавьте hostname вручную позже; главное на этом шаге — **скопировать токен** и ниже **CNAME**.

9. Cloudflare покажет строку для DNS, например:

   ```text
   app → xxxxxxxx-xxxx.cfargotunnel.com
   ```

   Скопируйте **`xxxxxxxx-xxxx.cfargotunnel.com`** (без `app`).

---

## ШАГ 3. REG.RU — DNS

reg.ru → **interviewaimvp.ru** → **DNS / Редактировать зону** → **Добавить**:

| Тип | Имя | Значение |
|-----|-----|----------|
| CNAME | `app` | `xxxxxxxx.cfargotunnel.com` *(из шага 2)* |

Сохранить. Подождать 10–30 мин.

**DNS-серверы REG.RU не менять.**

---

## ШАГ 4. Файл `.env` в проекте

```env
CLOUDFLARE_TUNNEL_TOKEN=eyJh...вставьте_токен_целиком...

PUBLIC_BASE_URL=https://app.interviewaimvp.ru
PUBLIC_FRONTEND_URL=https://app.interviewaimvp.ru
CORS_ORIGINS=https://app.interviewaimvp.ru,http://localhost:5173
```

Токен — одна длинная строка, **без** кавычек и пробелов в начале/конце.

---

## ШАГ 5. Запуск

**Терминал 1:**

```bash
./scripts/run-local.sh
```

**Терминал 2:**

```bash
./scripts/start-tunnel.sh
```

Должно быть `Registered tunnel connection`.

---

## ШАГ 6. Проверка

С телефона (мобильный интернет): **https://app.interviewaimvp.ru**

В админке **новая ссылка** на интервью → `https://app.interviewaimvp.ru/interview/...`

---

## Сообщение REG.RU «домен не подключён»

Исчезнет после рабочей CNAME (шаг 3) и когда туннель запущен (шаг 5).

---

## Ошибка: `does not have any RR of the requested type`

REG.RU и Cloudflare настроены верно (CNAME `app` → `….3439bfc.cfargotunnel.com`).  
Падает **локальный DNS** на ПК (часто корпоративная сеть `CAB-WSN-…`): не выдаёт IPv4 для `cfargotunnel.com`.

**Проверка:**

```bash
dig @8.8.8.8 app.interviewaimvp.ru A +short
```

Нужны адреса `104.x` / `172.x`. Если пусто — туннель должен быть **запущен** (`start-tunnel.sh`), подождите 2–5 мин.

**Что сделать:**

1. DNS в Ubuntu: **8.8.8.8**, **1.1.1.1** (настройки Wi‑Fi → IPv4).
2. `sudo resolvectl flush-caches`
3. Открыть сайт с **телефона** (мобильный интернет).
4. **Временно для демо** (без REG.RU):
   ```bash
   ./scripts/start-quick-tunnel.sh
   ```
   Скопировать `https://….trycloudflare.com` в `.env` → `PUBLIC_BASE_URL` и `PUBLIC_FRONTEND_URL`.

`curl --resolve …:198.41.…` + SSL error — **не использовать**, IP вручную не подходит.

---

## Кратко

| Где | Что |
|-----|-----|
| Cloudflare Zero Trust | Туннель + токен + Public Hostname |
| REG.RU | CNAME `app` → `….cfargotunnel.com` |
| `.env` | `CLOUDFLARE_TUNNEL_TOKEN` + URL https://app... |
| ПК | `run-local.sh` + `start-tunnel.sh` |

**Не нужно:** переносить .ru в Cloudflare, `cloudflared tunnel login`, пустой список зон.
