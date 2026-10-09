# Быстрый туннель (trycloudflare.com)

## Почему «перестал работать»

Quick tunnel **не постоянный**. Каждый запуск `./scripts/start-quick-tunnel.sh` выдаёт **новый** URL. Старый (в `.env`, закладках, ссылках кандидату) после остановки `cloudflared` **исчезает из DNS** — браузер показывает «не удаётся найти сайт» / NXDOMAIN.

Это не поломка кода: нужно снова запустить туннель и использовать **новый** адрес.

## Правильный порядок (2 терминала)

**Терминал 1:**

```bash
./scripts/run-local.sh
```

Дождитесь `Backend OK` и `Frontend: http://localhost:5173`.

**Терминал 2:**

```bash
./scripts/start-quick-tunnel.sh
```

Скопируйте URL из блока `Актуальный URL` (или из файла `.quick-tunnel-url`).

**Терминал 1** (если скрипт обновил `.env`): Ctrl+C и снова `./scripts/run-local.sh`.

## Админка и ссылки

- Открывайте админку **только по текущему** `https://….trycloudflare.com`, не по `localhost` и не по старому trycloudflare.
- После смены URL нажмите **«Сгенерировать ссылку»** ещё раз.

## VPN

Если trycloudflare открывается только через VPN — это ограничение сети/Cloudflare в вашем регионе, не приложения.

## Отключить авто-обновление .env

```bash
UPDATE_ENV=0 ./scripts/start-quick-tunnel.sh
```
