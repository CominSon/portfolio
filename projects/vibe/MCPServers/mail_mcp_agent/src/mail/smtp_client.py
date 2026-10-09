"""SMTP: отправка писем с вложениями."""

import logging
import mimetypes
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.mail import mail_auth, profile_store
from mail_mcp_agent.src.utils.path_resolver import resolve_attachment_path

logger = logging.getLogger("mail_mcp.smtp")


def send_email(
    to_addresses,
    subject,
    body,
    cc=None,
    attachment_paths=None,
    from_address=None,
):
    if not to_addresses:
        raise ValueError("Укажите хотя бы одного получателя (to)")

    sender = (from_address or profile_store.get_my_email() or "").strip()
    if not sender:
        profile_store.sync_from_noterball()
        sender = profile_store.get_my_email()
    if not sender:
        raise ValueError(
            "Email отправителя (From) не определён. "
            "Спросите у пользователя корпоративный адрес (например ivanov_iu@omega.sbrf.ru) "
            "и вызовите set_my_email(email=...). "
            "healthcheck_mail не смог определить email автоматически "
            "(нет строки в pen_is / Outlook не запущен)."
        )

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to_addresses)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or ""
    msg.attach(MIMEText(body or "", "plain", "utf-8"))

    attached_files = []
    for path_str in attachment_paths or []:
        path, size_mb = resolve_attachment_path(path_str)
        if size_mb > settings.MAX_ATTACHMENT_MB:
            raise ValueError(
                "Вложение {0} превышает лимит {1} МБ".format(
                    path.name, settings.MAX_ATTACHMENT_MB
                )
            )
        mime_type, _ = mimetypes.guess_type(str(path))
        mime_type = mime_type or "application/octet-stream"
        with path.open("rb") as handle:
            part = MIMEApplication(handle.read(), Name=path.name)
        part["Content-Type"] = mime_type
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        msg.attach(part)
        attached_files.append(str(path))

    recipients = list(to_addresses)
    if cc:
        recipients.extend(cc)

    creds = mail_auth.ensure_credentials()
    login = creds["login"]
    password = creds["password"]

    if settings.MAIL_DEBUG_LOG_CREDENTIALS:
        mail_auth._log_auth_attempt(
            "SMTP",
            login,
            password,
            extra=[
                "host={0}".format(settings.SMTP_HOST),
                "port={0}".format(settings.SMTP_PORT),
                "starttls=True",
            ],
        )

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60) as server:
            server.ehlo()
            try:
                server.starttls()
                server.ehlo()
            except smtplib.SMTPException:
                logger.debug("STARTTLS недоступен")
            server.login(login, password)
            server.sendmail(sender, recipients, msg.as_string())
        logger.info("SMTP OK mail_login=%s", login)
    except (smtplib.SMTPException, OSError) as exc:
        raise RuntimeError(
            "Ошибка SMTP ({0}:{1}, mail_login={2}): {3}".format(
                settings.SMTP_HOST, settings.SMTP_PORT, login, exc
            )
        ) from exc

    return {
        "ok": True,
        "from": sender,
        "to": to_addresses,
        "cc": cc or [],
        "subject": subject,
        "attachments": attached_files,
    }
