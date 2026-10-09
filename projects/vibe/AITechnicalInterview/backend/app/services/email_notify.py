"""Уведомления на почту (SMTP из .env). Без SMTP — только лог."""
import logging
import re
import smtplib
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from uuid import UUID

from app.config import fresh_settings, get_settings
from app.services.report_format import format_report_text_ru

logger = logging.getLogger(__name__)

_ASCII_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _montage_link(interview_id: UUID) -> str:
    """Публичная ссылка через frontend (Vite проксирует /api на :8000)."""
    base = fresh_settings().frontend_public_url.rstrip("/")
    return f"{base}/api/v1/interviews/{interview_id}/recordings/montage"


def _video_pending_notice() -> str:
    hours = get_settings().montage_email_delay_hours
    word = "ЧАС" if hours == 1 else "ЧАСА" if 2 <= hours <= 4 else "ЧАСОВ"
    return (
        "\n"
        + "!" * 60
        + "\n"
        + "ВНИМАНИЕ: ВИДЕО ИНТЕРВЬЮ БУДЕТ НАПРАВЛЕНО ОТДЕЛЬНЫМ ПИСЬМОМ\n"
        + f"ПРИМЕРНО ЧЕРЕЗ {hours} {word} ПОСЛЕ ЗАВЕРШЕНИЯ ИНТЕРВЬЮ.\n"
        + "!" * 60
        + "\n"
    )


def build_report_email_body(
    report_data: dict,
    interview_meta: dict | None,
    interview_id: UUID,
    *,
    video_pending: bool = False,
) -> str:
    """Текст первого письма: только отчёт, без ссылки на видео."""
    body = format_report_text_ru(report_data, interview_meta)
    body += "\n\n" + "—" * 60 + "\nВИДЕО ИНТЕРВЬЮ\n" + "—" * 60 + "\n"
    if video_pending:
        body += _video_pending_notice()
    else:
        body += (
            "Запись интервью направляется отдельным письмом со ссылкой на MP4.\n"
            "Если письма с видео нет — проверьте папку «Спам» или обратитесь к администратору.\n"
        )
    return body


def build_video_email_body(
    interview_id: UUID,
    interview_meta: dict | None = None,
    report_data: dict | None = None,
) -> str:
    """Текст письма: итоги оценки AI и ссылки на видео/стенограмму."""
    from app.services.interview_montage_service import montage_is_ready

    montage_url = _montage_link(interview_id)
    transcript_url = f"{fresh_settings().frontend_public_url.rstrip('/')}/api/v1/interviews/{interview_id}/transcript.txt"
    lines = [
        "Техническое интервью завершено.",
        "",
    ]
    if interview_meta:
        name = interview_meta.get("candidate_name") or ""
        if name:
            lines.append(f"Кандидат: {name}")
        fmt = interview_meta.get("format") or ""
        if fmt:
            lines.append(f"Формат: {fmt}")
        started = interview_meta.get("started_at") or ""
        ended = interview_meta.get("ended_at") or ""
        if started or ended:
            lines.append(f"Период: {started} — {ended}")
        lines.append("")
    if report_data:
        lines.extend(
            [
                "Итоги оценки AI:",
                "",
                format_report_text_ru(report_data, interview_meta),
                "",
            ]
        )
    lines.extend(
        [
            "—" * 60,
            "Материалы записи",
            "—" * 60,
            "",
            "Раскладка: слева — демонстрация экрана, справа — веб-камера, звук с микрофона.",
            "",
            f"Ссылка на MP4:\n  {montage_url}",
            "",
            f"Стенограмма (txt):\n  {transcript_url}",
        ]
    )
    if not montage_is_ready(interview_id):
        lines.append(
            "\nПримечание: файл ещё собирается. Если ссылка не открывается — "
            "повторите через несколько минут."
        )
    return "\n".join(lines)


def _normalize_recipients(to_addresses: list[str]) -> tuple[list[str], str | None]:
    """Проверить адреса: SMTP принимает только латиницу (ASCII)."""
    recipients: list[str] = []
    for raw in to_addresses:
        addr = str(raw).strip()
        if not addr:
            continue
        try:
            addr.encode("ascii")
        except UnicodeEncodeError:
            return [], (
                f"Некорректный email «{addr}»: в адресе есть кириллица или другие "
                f"не-ASCII символы. Укажите реальный ящик латиницей, например "
                f"name@mail.ru — не подставляйте «ваш@email.ru» из примеров в документации."
            )
        if not _ASCII_EMAIL_RE.match(addr):
            return [], f"Некорректный формат email: «{addr}»"
        recipients.append(addr)
    return recipients, None


def _send_plain_email(to_addresses: list[str], subject: str, body_text: str) -> bool:
    recipients, err = _normalize_recipients(to_addresses)
    if err:
        logger.error("Email: %s", err)
        print(err)
        return False
    if not recipients:
        logger.info("Email: нет получателей")
        return False

    settings = get_settings()
    if not settings.smtp_host:
        logger.info(
            "Email не отправлен (SMTP_HOST не задан). Получатели: %s. Тема: %s",
            recipients,
            subject,
        )
        logger.info("Текст:\n%s", body_text[:4000])
        return False

    from_addr = settings.email_from or settings.smtp_user or "interview@localhost"
    display = (settings.email_from_name or "").strip()
    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(display, "utf-8")), from_addr)) if display else from_addr
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(body_text, "plain", "utf-8"))

    try:
        use_ssl = settings.smtp_port == 465 or settings.smtp_use_ssl
        smtp_cls = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP

        with smtp_cls(settings.smtp_host, settings.smtp_port, timeout=60) as smtp:
            if not use_ssl and settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_user and settings.smtp_password:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(from_addr, recipients, msg.as_string())
        logger.info("Email отправлен: %s — %s", recipients, subject)
        return True
    except smtplib.SMTPAuthenticationError as exc:
        err = str(exc).lower()
        if "prilozheniya" in err or "application password" in err:
            logger.error(
                "Mail.ru отклонил вход: нужен пароль для внешнего приложения "
                "(id.mail.ru → Безопасность), не пароль от входа в почту. %s",
                recipients,
            )
        else:
            logger.exception("SMTP auth failed for %s", recipients)
        return False
    except Exception:
        logger.exception("Email send failed to %s", recipients)
        return False


def send_report_email(
    to_addresses: list[str],
    subject: str,
    body_text: str,
    report_data: dict | None = None,
    interview_meta: dict | None = None,
    interview_id: UUID | None = None,
    *,
    video_pending: bool = False,
) -> bool:
    if report_data and interview_id:
        body_text = build_report_email_body(
            report_data, interview_meta, interview_id, video_pending=video_pending
        )
    elif report_data:
        body_text = format_report_text_ru(report_data, interview_meta)

    return _send_plain_email(to_addresses, subject, body_text)


def send_video_email(
    to_addresses: list[str],
    interview_id: UUID,
    interview_meta: dict | None = None,
    report_data: dict | None = None,
) -> bool:
    body = build_video_email_body(interview_id, interview_meta, report_data)
    name = (interview_meta or {}).get("candidate_name") or ""
    subject = f"AI-интервью: {name}" if name else f"AI-интервью {interview_id}"
    return _send_plain_email(to_addresses, subject, body)
