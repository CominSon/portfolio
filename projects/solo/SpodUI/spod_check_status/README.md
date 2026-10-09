# spod_check_status

Мониторинг статусов загрузок в СПОД и синхронизация прогресса в Greenplum.

## Кратко

Берёт cookies активной сессии, ходит в API СПОД, сопоставляет статусы загрузок с записями в `logs_spod_process` / связанных лог-таблицах, обновляет стадии процесса и формирует/отправляет уведомления по результатам.

## Техстек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.6.1 |
| UI-автоматизация | Selenium (получение/использование cookies) |
| HTTP / API | requests |
| БД | Greenplum + SQLAlchemy |
| Данные | pandas |
| Auth | cookies от otp_support / Selenium |

## Структура

```
spod_check_status/
  spod_check_status.txt
  README.md
  src/
    main.py      # Connect, Working, Sending, Main
    settings.py
    logs/
```
