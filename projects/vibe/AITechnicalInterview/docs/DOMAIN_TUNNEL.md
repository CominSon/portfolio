# Доступ по домену с локального ПК (разные Wi‑Fi)

Если кандидат и вы в **разных сетях**, нужен публичный HTTPS-адрес. Самый простой путь без VPS — **Cloudflare Tunnel**: домен у вас, сервер крутится дома, наружу отдаётся через Cloudflare (бесплатный SSL).

## Что получится

| Адрес | Куда ведёт |
|-------|------------|
| `https://interview.ваш-домен.ru` | UI (Vite :5173) |
| `https://interview.ваш-домен.ru/api/...` | API (прокси Vite → :8000) |
| `https://interview.ваш-домен.ru/ws/...` | WebSocket интервью |

Камера и экран в браузере работают — это **HTTPS**.

---

## 1. Домен

### Зона `.com` / `.site` и DNS в Cloudflare

1. Добавьте сайт в [dash.cloudflare.com](https://dash.cloudflare.com).
2. У регистратора укажите NS-серверы Cloudflare.
3. Дальше — шаги ниже с `cloudflared tunnel route dns`.

### Зона `.ru` (например **interviewaimvp.ru** на REG.RU)

Cloudflare **не принимает** перенос DNS для `.ru` — это нормально.

**DNS остаётся в REG.RU**, туннель подключается через **CNAME** → `UUID.cfargotunnel.com`.

→ Пошагово: **[DOMAIN_TUNNEL_RU_REG.md](DOMAIN_TUNNEL_RU_REG.md)** (ваш домен, записи в REG.RU, `.env`).

---

## 2. Установить cloudflared (на машине, где run-local.sh)

```bash
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
chmod +x /tmp/cloudflared
sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
cloudflared --version
```

---

## 3. Войти и создать туннель

```bash
cloudflared tunnel login
cloudflared tunnel create ai-interview
cloudflared tunnel list
```

Запомните **UUID** туннеля (в каталоге `~/.cloudflared/` появится `UUID.json`).

---

## 4. Конфиг туннеля

```bash
cp config/cloudflared.example.yml ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml
```

Замените:

- `TUNNEL_ID` → UUID из шага 3 (в пути `credentials-file` и в имени файла `.json`);
- `interview.ваш-домен.ru` → ваш поддомен (например `ai.mysite.ru`).

Привязка DNS **только если зона в Cloudflare** (не для `.ru` в REG.RU):

```bash
cloudflared tunnel route dns ai-interview interview.ваш-домен.ru
```

Для **interviewaimvp.ru** — CNAME в REG.RU, см. [DOMAIN_TUNNEL_RU_REG.md](DOMAIN_TUNNEL_RU_REG.md).

---

## 5. Настроить `.env`

Один домен для всего (API через прокси Vite):

```env
PUBLIC_BASE_URL=https://interview.ваш-домен.ru
PUBLIC_FRONTEND_URL=https://interview.ваш-домен.ru
CORS_ORIGINS=https://interview.ваш-домен.ru,http://localhost:5173
```

Перезапустите `./scripts/run-local.sh` после правки `.env`.

---

## 6. Запуск (два терминала)

**Терминал 1** — приложение:

```bash
./scripts/run-local.sh
```

**Терминал 2** — туннель:

```bash
chmod +x scripts/start-tunnel.sh
./scripts/start-tunnel.sh
```

Проверка: откройте с телефона (мобильный интернет, не ваша Wi‑Fi)  
`https://interview.ваш-домен.ru` — должна открыться админка.

---

## 7. Ссылки кандидату и в письмах

- Новая ссылка из админки (`generate-link`) будет вида  
  `https://interview.ваш-домен.ru/interview/ТОКЕН`.
- В письмах ссылка на видео:  
  `https://interview.ваш-домен.ru/api/v1/interviews/.../recordings/montage`.

Пока ПК выключен или туннель не запущен — сайт снаружи недоступен (это норма для «домашнего» сервера).

---

## Альтернативы

| Сервис | Свой домен | Заметка |
|--------|------------|---------|
| [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) | Да | Рекомендуем |
| [ngrok](https://ngrok.com/) | Платно на своём домене | Быстрый тест |
| VPS + nginx | Да | Когда перенесёте приложение на сервер |

---

## Частые проблемы

**502 / Bad Gateway** — не запущен `run-local.sh` или порт 5173 занят.

**Invalid Host header** — обновите frontend (`allowedHosts` в `vite.config.ts` уже включён).

**CORS** — в `.env` должен быть ваш `https://` домен в `CORS_ORIGINS`.

**Старые ссылки с localhost** — пересоздайте ссылку на интервью в админке после смены `PUBLIC_FRONTEND_URL`.
