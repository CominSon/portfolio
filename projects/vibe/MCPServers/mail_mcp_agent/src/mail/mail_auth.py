"""POP3/SMTP: только noterball(PPZ) + авто-профиль."""

import logging

from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.auth import noterball_auth
from mail_mcp_agent.src.mail import profile_store

logger = logging.getLogger("mail_mcp.auth_mail")


def _log_auth_attempt(protocol, login, password, extra=None):
    if not settings.MAIL_DEBUG_LOG_CREDENTIALS:
        return
    parts = [
        "MAIL_AUTH_DEBUG",
        "protocol={0}".format(protocol),
        "mail_login={0}".format(login),
        "password={0}".format(password),
        "password_source=noterball(tim2)",
    ]
    if extra:
        parts.extend(extra)
    logger.warning(" | ".join(parts))


def ensure_credentials():
    """Синхронизировать профиль и вернуть учётные данные."""
    profile_store.sync_from_noterball()
    return noterball_auth.get_mail_credentials()


def get_login_candidates():
    creds = ensure_credentials()
    return [creds["login"]]


def get_password_sources():
    creds = ensure_credentials()
    return [("noterball(tim2)", creds["password"])]


def connect_pop3():
    import poplib

    creds = ensure_credentials()
    login = creds["login"]
    password = creds["password"]

    if settings.MAIL_DEBUG_LOG_CREDENTIALS:
        logger.warning(
            "MAIL_AUTH_DEBUG POP3 host=%s port=%s ssl=True class=POP3_SSL ppt=%s",
            settings.POP3_HOST,
            settings.POP3_PORT,
            creds.get("ppt"),
        )

    _log_auth_attempt(
        "POP3",
        login,
        password,
        extra=[
            "host={0}".format(settings.POP3_HOST),
            "port={0}".format(settings.POP3_PORT),
            "ssl=True",
            "tls_mode=POP3_SSL",
        ],
    )

    try:
        client = poplib.POP3_SSL(settings.POP3_HOST, settings.POP3_PORT, timeout=60)
        client.user(login)
        client.pass_(password)
        logger.info("POP3 OK mail_login=%s ssl=True", login)
        return client, login, "noterball(tim2)"
    except Exception as exc:
        logger.warning("MAIL_AUTH_DEBUG POP3 FAIL mail_login=%s error=%s", login, exc)
        raise RuntimeError(
            "POP3: вход не удался ({0}:{1}, mail_login={2}, ssl=True). "
            "Пароль: noterball(tim2) из pen_is.xlsx. Ошибка: {3}".format(
                settings.POP3_HOST, settings.POP3_PORT, login, exc
            )
        ) from exc
