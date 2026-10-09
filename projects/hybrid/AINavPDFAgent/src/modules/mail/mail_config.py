import os


class IMAPConfig:
    MAIL_IMAP_SERVER = "imap.sigma.sbrf.ru"
    MAIL_IMAP_PORT = 993
    MAIL_USER = os.getenv("MAIL_USER")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_CHECK_INTERVAL = 5  # интервал проверки (сек)


class SMTPConfig:
    SMTP_SERVER = "smtp.sberbank.ru"
    SMTP_PORT = 587
    SMTP_USER = os.getenv("MAIL_USER_FOR_SEND")
    SMTP_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_FROM = os.getenv("MAIL_FROM")
