import os
import smtplib
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
import email.utils
from typing import Optional
import re
from src.modules.common.common_manager import CommonManager
from src.modules.mail.mail_config import SMTPConfig


class SMTPManager:
    """ Отправка писем + ответ в ту же переписку (In-Reply-To / References). """

    def __init__(self, logger):
        self.logger = logger
        self.smtp_config: SMTPConfig = SMTPConfig()
        self.common_manager: CommonManager = CommonManager()

    def _connect(self):
        server = smtplib.SMTP(self.smtp_config.SMTP_SERVER, self.smtp_config.SMTP_PORT, timeout=30)
        server.ehlo()
        server.starttls()
        server.login(self.smtp_config.SMTP_USER, self.smtp_config.SMTP_PASSWORD)
        return server

    @staticmethod
    def _sanitize_header(value: str | None) -> str:
        """Удаляет переносы строк и лишние пробелы из заголовков письма."""
        if not value:
            return ""
        return value.replace("\r", "").replace("\n", "").strip()

    @staticmethod
    def _make_reply_subject(src_subject: str) -> str:
        s = SMTPManager._sanitize_header(src_subject)
        return s if s.lower().startswith("re:") else f"Re: {s}"

    def _build_message(self,
                       to_addr: str,
                       subject: str,
                       text: str,
                       html: Optional[str] = None,
                       in_reply_to: Optional[str] = None,
                       references: Optional[str] = None) -> EmailMessage:
        try:
            msg = EmailMessage()
            msg["From"] = self._sanitize_header(self.smtp_config.MAIL_FROM)
            msg["To"] = self._sanitize_header(to_addr)
            msg["Subject"] = self._sanitize_header(subject)
            msg["Date"] = formatdate(localtime=True)
            if in_reply_to:
                msg["In-Reply-To"] = self._sanitize_header(in_reply_to)
            if references:
                msg["References"] = self._sanitize_header(references)
            msg.set_content(text or "")
            if html:
                msg.add_alternative(html, subtype="html")
            msg["Message-ID"] = make_msgid()
            return msg
        except Exception as e:
            self.logger.error(f"[SMTP] Ошибка формирования сообщения для ответа: {e}")

    def send(self, msg: EmailMessage):
        try:
            self.logger.info(
                "[SMTP] Отправка письма: "
                f"To={msg['To']}, Subject={msg['Subject']}, "
                f"In-Reply-To={msg.get('In-Reply-To')}, References={msg.get('References')}"
            )
            with self._connect() as s:
                s.send_message(msg)
            self.logger.info("[SMTP] Письмо отправлено")
        except Exception as e:
            self.logger.error(f"[SMTP] Ошибка отправки: {e}")

    # ========== публичные методы ==========

    def send_reply(self, original_msg, text: str, html: str | None = None, subject_override: str | None = None):
        """
        Ответить в СУЩЕСТВУЮЩУЮ переписку.
        :param text:
        :param html:
        :param subject_override:
        :param original_msg: словарь из IMAPManager (важно: from_email, subject, message_id, references?)
        """
        try:
            if isinstance(original_msg, dict):
                to_addr = original_msg.get("from_email")
                if not to_addr and "from" in original_msg:
                    #to_addr = email.utils.parseaddr(original_msg["from"])[1]
                    match = re.search(r'<([^>]+)>', original_msg["from"])
                    if match:
                        to_addr = match.group(1)
                    else:
                        to_addr = email.utils.parseaddr(original_msg["from"])[1]

                orig_subj = original_msg.get("subject", "")
                in_reply_to = original_msg.get("message_id")
                refs = original_msg.get("references")
            else:
                to_addr = original_msg.get("From")
                orig_subj = original_msg.get("Subject", "")
                in_reply_to = original_msg.get("Message-ID")
                refs = " ".join(original_msg.get_all("References", [])) if original_msg.get_all("References") else None

            if not refs and in_reply_to:
                refs = in_reply_to

            subj = subject_override or self._make_reply_subject(orig_subj)
            msg = self._build_message(
                to_addr=to_addr,
                subject=subj,
                text=text,
                html=html,
                in_reply_to=in_reply_to,
                references=refs
            )
            self.send(msg)

        except Exception as e:
            self.logger.error(f"[SMTP] Ошибка send_reply: {e}")

    def notify_pdf_start(self, original_msg: dict, urls: list[str], mode_int: int, color_int: int):
        """
        Отправка уведомления заказчику, что началась генерация PDF.
        :param original_msg: словарь письма (из IMAPManager)
        :param urls: список ссылок
        :param mode_int: 0 = пром, 1 = предпросмотр
        """
        try:
            count_urls = len(urls)
            urls_block = "\n".join(f"{i+1}.{u}" for i, u in enumerate(urls))
            mode_str = 'Предпросмотр' if mode_int == 1 else 'Промышленный'
            color_str = 'Темная' if color_int == 1 else 'Светлая'
            estimated = self.common_manager.get_estimated_time_str(count=count_urls)
            text = (
                "Принял задачу. Начинаю формировать PDF.\n"
                f"Количество ссылок: {count_urls}:\n"
                f"--------------------------------\n"
                f"{urls_block}\n"
                f"--------------------------------\n"
                f"Режим: {mode_str}\n"
                f"Тема: {color_str}\n"
                f"{estimated}."
            )
            self.send_reply(original_msg=original_msg, text=text)
            self.logger.info(
                    f"[SMTP] Уведомление о старте PDF отправлено "
                    f"(ссылок={len(urls)}, режим={mode_int})"
            )
        except Exception as e:
            self.logger.error(f"[SMTP] Ошибка при отправке уведомления о старте PDF: {e}")

    def send_reply_with_attachment(
            self,
            original_msg,
            subject_override: str,
            text: str,
            attachments: list[str]
    ):
        try:
            if isinstance(original_msg, dict):
                to_addr = original_msg.get("from_email")
                if not to_addr and "from" in original_msg:
                    import email.utils
                    match = re.search(r'<([^>]+)>', original_msg["from"])
                    if match:
                        to_addr = match.group(1)
                    else:
                        to_addr = email.utils.parseaddr(original_msg["from"])[1]

                orig_subj = original_msg.get("subject", "")
                in_reply_to = original_msg.get("message_id")
                refs = original_msg.get("references")
            else:
                to_addr = original_msg.get("From")
                orig_subj = original_msg.get("Subject", "")
                in_reply_to = original_msg.get("Message-ID")
                refs = " ".join(original_msg.get_all("References", [])) if original_msg.get_all("References") else None

            if not to_addr:
                self.logger.error(f"[SMTP] Не удалось определить адрес получателя! original_msg={original_msg}")
                return

            subj = subject_override or self._make_reply_subject(orig_subj)
            msg = self._build_message(
                to_addr=self._sanitize_header(to_addr),
                subject=subj,
                text=text,
                in_reply_to=in_reply_to,
                references=refs
            )

            for path in attachments:
                with open(path, "rb") as f:
                    data = f.read()
                    msg.add_attachment(
                        data,
                        maintype="application",
                        subtype="pdf",
                        filename=os.path.basename(path)
                    )

            self.logger.info(f"[SMTP] Отправка письма: To={to_addr}, Subject={subj}")
            self.send(msg)

        except Exception as e:
            import traceback
            self.logger.error(f"[SMTP] Ошибка отправки письма с вложением: {e}\n{traceback.format_exc()}")



