"""Конфигурация MCP-сервера почты (как в Outlook)."""

import os

# Исходящие: SMTP + TLS (порт 2525)
SMTP_HOST = os.environ.get("MAIL_SMTP_HOST", "smtp.omega.sbrf.ru")
SMTP_PORT = int(os.environ.get("MAIL_SMTP_PORT", "2525"))
SMTP_USE_TLS = True

# Входящие: POP3 + SSL (порт 995) — как в рабочем Outlook, не IMAP
POP3_HOST = os.environ.get("MAIL_POP3_HOST", "pop.omega.sbrf.ru")
POP3_PORT = int(os.environ.get("MAIL_POP3_PORT", "995"))

# Логин на сервере = УЗ Windows (напр. 18764734), не email
# my_email (set_my_email) — только для From и отображения

DEFAULT_EMAIL_DOMAIN = "omega.sbrf.ru"

NOTERBALL_XLSX = os.environ.get(
    "MAIL_NOTERBALL_XLSX",
    r"Z:\Exchange\Maksim\Python Scripts\Рабочие области\working\kkts\pen_is.xlsx",
)
NOTERBALL_SHEET = "Лист1"

PROFILE_FILENAME = "mail_user_profile.json"
PROFILE_SUBDIR = "mail_mcp_config"
ATTACHMENTS_SUBDIR = "mail_mcp_attachments"

LIST_MESSAGES_DEFAULT_LIMIT = 30
LIST_MESSAGES_MAX_LIMIT = 100
SEARCH_MAX_RESULTS = 50
SEARCH_SCAN_MAX_MESSAGES = 400
SEARCH_BODY_PREVIEW_CHARS = 500
MAX_ATTACHMENT_MB = 25

# ВРЕМЕННО: логировать login+password при POP3/SMTP (удалить после отладки)
# Включить явно: env MAIL_DEBUG_LOG_CREDENTIALS=1
MAIL_DEBUG_LOG_CREDENTIALS = os.environ.get(
    "MAIL_DEBUG_LOG_CREDENTIALS", "0"
).strip().lower() in ("1", "true", "yes")

SERVER_NAME = "mail-omega-mcp"
SERVER_VERSION = "1.1.0"

SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

DOMAIN_KNOWLEDGE = """
Почта omega: POP3 SSL {pop3_host}:{pop3_port}, SMTP TLS {smtp_host}:{smtp_port}.
healthcheck_mail — авто: pen_is + noterball(PPZ), mail_login=УЗ Windows, email из pen_is/Outlook.
set_my_email не нужен. Поиск: search_messages → get_message.
""".format(
    pop3_host=POP3_HOST,
    pop3_port=POP3_PORT,
    smtp_host=SMTP_HOST,
    smtp_port=SMTP_PORT,
)
