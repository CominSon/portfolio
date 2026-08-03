# spod_otp_support

Сервис поддержки OTP-авторизации и актуальных cookies для скриптов СПОД.

## Кратко

Долгоживущий процесс: логинится в веб-СПОД через Selenium (СУДИР + OTP), сохраняет cookies и периодически обновляет сессию (~каждые 10 минут), чтобы остальные скрипты могли ходить в API/UI без повторного ручного ввода OTP.

## Техстек

| Компонент | Технология |
|-----------|------------|
| Язык | Python 3.6.1 |
| UI-автоматизация | Selenium, Firefox, geckodriver |
| HTTP | requests.Session |
| Конфиг | settings + Excel с зашифрованными учётными данными |
| Auth | `noterball` (расшифровка), cookies в `results/` |
| БД | не обязательна для основного цикла (SQLAlchemy/connectBD в settings) |

## Структура

```
spod_otp_support/
  spod_otp_support.txt
  README.md
  src/
    main.py
    settings.py
    logs/          # пример OTP-логов
    results/       # cookies / profile
```
