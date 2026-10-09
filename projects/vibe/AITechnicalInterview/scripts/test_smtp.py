#!/usr/bin/env python3
"""Проверка SMTP: отправка тестового письма с технического ящика из .env."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings
from app.services.email_notify import send_report_email


def main() -> None:
    if len(sys.argv) < 2:
        print("Использование: python scripts/test_smtp.py recipient@example.com")
        sys.exit(1)

    to = sys.argv[1].strip()
    s = get_settings()

    if not s.smtp_host:
        print("Ошибка: SMTP_HOST не задан в .env")
        print("См. docs/TECHNICAL_EMAIL.md")
        sys.exit(1)
    if not s.smtp_password:
        print("Ошибка: SMTP_PASSWORD пустой.")
        print("Mail.ru: id.mail.ru → Пароли для внешних приложений (см. docs/TECHNICAL_EMAIL.md)")
        print("См. docs/TECHNICAL_EMAIL.md")
        sys.exit(1)

    print(f"Отправка с: {s.email_from or s.smtp_user} ({s.smtp_host}:{s.smtp_port})")
    print(f"Получатель: {to}")

    ok = send_report_email(
        [to],
        subject="[AI Interview] Тест SMTP",
        body_text=(
            "Тестовое письмо от платформы AI Technical Interview.\n\n"
            "Если вы видите это сообщение — техническая почта настроена верно."
        ),
    )
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
