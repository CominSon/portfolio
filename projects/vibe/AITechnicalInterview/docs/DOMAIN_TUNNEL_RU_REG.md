# interviewaimvp.ru + Cloudflare Tunnel (DNS в REG.RU)

Сообщение Cloudflare **«домен .ru не поддерживается»** относится к **переносу DNS-зоны** в Cloudflare (смена NS). Это **не мешает** использовать **Cloudflare Tunnel** с доменом, купленным на REG.RU.

Схема:

```
interviewaimvp.ru  →  DNS в REG.RU (как сейчас)
       ↓ CNAME на *.cfargotunnel.com
Cloudflare Tunnel (cloudflared на вашем ПК)
       ↓
localhost:5173 (run-local.sh)
```

---

## 0. Установка cloudflared (если «команда не найдена»)

В Linux пакет **не ставится** вместе с проектом. Из каталога репозитория:

```bash
chmod +x scripts/install-cloudflared.sh
./scripts/install-cloudflared.sh
```

В `~/.bashrc` добавьте (если скрипт подскажет):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Новый терминал или `source ~/.bashrc`, затем:

```bash
cloudflared --version
```

---

## 1. Cloudflared (один раз)

```bash
cloudflared tunnel login
cloudflared tunnel create ai-interview
cloudflared tunnel list
```

Скопируйте **UUID** туннеля (колонка ID).  
Цель для CNAME: **`UUID.cfargotunnel.com`** (подставьте свой UUID).

---

## 2. Конфиг туннеля

```bash
mkdir -p ~/.cloudflared
cp config/cloudflared.interviewaimvp.example.yml ~/.cloudflared/config.yml
nano ~/.cloudflared/config.yml
```

В `credentials-file` укажите путь к `~/.cloudflared/UUID.json`.

**Не выполняйте** `cloudflared tunnel route dns` для `.ru` — эта команда для зон в Cloudflare DNS.

---

## 3. Запись в REG.RU

[reg.ru](https://www.reg.ru) → **Мои домены** → `interviewaimvp.ru` → **DNS-серверы и зона** → **Редактировать зону**.

### Вариант A (рекомендуется): поддомен `app`

| Тип | Имя | Значение |
|-----|-----|----------|
| CNAME | `app` | `ВАШ-UUID.cfargotunnel.com` |

Сайт: **https://app.interviewaimvp.ru**

Корень `interviewaimvp.ru` можно позже настроить **перенаправление** на `app` в панели REG.RU (если есть «Переадресация домена»).

### Вариант B: `www`

| Тип | Имя | Значение |
|-----|-----|----------|
| CNAME | `www` | `ВАШ-UUID.cfargotunnel.com` |

Сайт: **https://www.interviewaimvp.ru**

> На корне `@` у `.ru` часто **нельзя** CNAME — только A-запись на IP. Туннелю нужен именно **CNAME**, поэтому используйте `app` или `www`.

TTL: 300–3600 сек. Сохраните зону, подождите 5–30 минут.

---

## 4. `.env` в проекте

Для **app** (подставьте свой вариант URL):

```env
PUBLIC_BASE_URL=https://app.interviewaimvp.ru
PUBLIC_FRONTEND_URL=https://app.interviewaimvp.ru
CORS_ORIGINS=https://app.interviewaimvp.ru,http://localhost:5173
```

Для **www**:

```env
PUBLIC_BASE_URL=https://www.interviewaimvp.ru
PUBLIC_FRONTEND_URL=https://www.interviewaimvp.ru
CORS_ORIGINS=https://www.interviewaimvp.ru,http://localhost:5173
```

Перезапустите `./scripts/run-local.sh`.

---

## 5. Запуск

**Терминал 1:**

```bash
./scripts/run-local.sh
```

**Терминал 2:**

```bash
./scripts/start-tunnel.sh
```

Проверка с телефона (мобильный интернет): `https://app.interviewaimvp.ru`

---

## 6. Ссылки кандидату

После смены `.env` в админке заново **сгенерируйте ссылку** на интервью — будет:

`https://app.interviewaimvp.ru/interview/ТОКЕН`

---

## Если туннель не поднимается

```bash
cloudflared tunnel info ai-interview
cloudflared tunnel run ai-interview --config ~/.cloudflared/config.yml
```

**502** — не запущен `run-local.sh`.  
**DNS не резолвится** — подождите или проверьте CNAME в REG.RU (без `http://`, только имя `UUID.cfargotunnel.com`).

---

## Альтернатива без Cloudflare

Если туннель не устроит: **ngrok** (платный свой домен) или **VPS в РФ** + nginx + Let's Encrypt — см. [DOMAIN_TUNNEL.md](DOMAIN_TUNNEL.md).
