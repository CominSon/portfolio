# spod_approve_load

Автоподтверждение загрузок в СПОД после успешной подготовки/отправки данных.

## Кратко

Читает из Greenplum структуры, ожидающие подтверждения, поднимает API-сессию по cookies, находит id загрузок по структурам и вызывает approve в API СПОД. Статус в `logs_spod_process` обновляется автоматически.

## Техстек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.6.1 |
| UI-автоматизация | Selenium (cookies) |
| HTTP / API | requests (`load/operation/approve` и др.) |
| БД | Greenplum + SQLAlchemy |
| Данные | pandas |
| Auth | cookies от otp_support / Selenium |

## Структура

```
spod_approve_load/
  README.md
  src/
    main.py
    settings.py
    logs/        # примеры логов подтверждений
```
