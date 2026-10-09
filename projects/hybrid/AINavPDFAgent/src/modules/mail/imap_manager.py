import imaplib
import html as html_lib
import email
import re
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from email.message import EmailMessage
from html.parser import HTMLParser

from modules.mail.smtp_manager import SMTPManager
from src.modules.mail.mail_config import IMAPConfig


class _HTMLStripper(HTMLParser):
    """Простейший HTML→text без внешних зависимостей."""

    def __init__(self):
        super().__init__()
        self._parts = []

    def handle_data(self, d):
        self._parts.append(d)

    def get_text(self):
        text = " ".join(self._parts)
        # нормализация пробелов
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


class IMAPManager:
    """
    Класс для чтения писем через IMAP.
    """

    def __init__(self, logger):
        self.logger = logger
        self.imap_config: IMAPConfig = IMAPConfig()
        self.smtp_manager: SMTPManager = SMTPManager(logger=self.logger)
        self.mail: imaplib.IMAP4_SSL | None = None

    # ---------- utils ----------
    @staticmethod
    def _decode_header_value(value: str | None) -> str:
        if not value:
            return ""
        try:
            return str(make_header(decode_header(value)))
        except Exception:
            return value

    @staticmethod
    def _html_to_text(html: str) -> str:
        """
        Превращает HTML в обычный текст:
        - убирает <!--комментарии-->, <style>, <script>
        - вычищает теги
        - декодирует HTML-сущности (&nbsp; и т.п.)
        - нормализует пробелы/переводы строк
        """
        try:
            # удаляем комментарии
            html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
            # удаляем style/script блоки
            html = re.sub(r"<\s*(style|script)[^>]*>.*?<\s*/\s*\1\s*>", " ", html, flags=re.S | re.I)
            # выкидываем все теги
            html = re.sub(r"<[^>]+>", " ", html)
            # декодируем сущности (&nbsp; → пробел и т.д.)
            html = html_lib.unescape(html)
            # нормализуем пробелы
            html = re.sub(r"[ \t]+", " ", html)
            html = re.sub(r"\s*\n\s*", "\n", html)
            html = re.sub(r"\n{3,}", "\n\n", html)
            return html.strip()
        except Exception:
            return html

    @staticmethod
    def _extract_text_and_attachments(msg: EmailMessage) -> tuple[str, bool, list[str]]:
        """
        Возвращает (plain_text, has_attachments, attachment_names)
        Предпочтительно text/plain; если нет — берём text/html и превращаем в текст.
        """
        text = ""
        html = ""
        has_attachments = False
        attach_names: list[str] = []

        if msg.is_multipart():
            for part in msg.walk():
                cdisp = (part.get("Content-Disposition") or "").lower()
                ctype = (part.get_content_type() or "").lower()

                # вложение?
                filename = part.get_filename()
                if "attachment" in cdisp or filename:
                    has_attachments = True
                    if filename:
                        try:
                            filename = str(make_header(decode_header(filename)))
                        except Exception:
                            pass
                        attach_names.append(filename)
                    continue

                # текст
                if ctype == "text/plain" and not text:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        text = part.get_payload(decode=True).decode(charset, errors="ignore")
                    except Exception:
                        text = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                elif ctype == "text/html" and not html:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html = part.get_payload(decode=True).decode(charset, errors="ignore")
                    except Exception:
                        html = part.get_payload(decode=True).decode("utf-8", errors="ignore")
        else:
            ctype = (msg.get_content_type() or "").lower()
            if ctype == "text/plain":
                charset = msg.get_content_charset() or "utf-8"
                text = msg.get_payload(decode=True).decode(charset, errors="ignore")
            elif ctype == "text/html":
                charset = msg.get_content_charset() or "utf-8"
                html = msg.get_payload(decode=True).decode(charset, errors="ignore")

        if not text and html:
            text = IMAPManager._html_to_text(html)

        return text.strip(), has_attachments, attach_names

    # ---------- imap ----------
    def _ensure_selected(self, mailbox, readonly=False):
        # Выбор папки обязателен перед SEARCH
        status, _ = self.mail.select(mailbox, readonly=readonly)
        if status != "OK":
            raise RuntimeError(f"Не удалось выбрать папку {mailbox}")
        return status, _

    def connect(self):
        try:
            if not self.imap_config.MAIL_USER or not self.imap_config.MAIL_PASSWORD:
                raise RuntimeError("MAIL_USER/MAIL_PASSWORD пустые")
            self.mail = imaplib.IMAP4_SSL(self.imap_config.MAIL_IMAP_SERVER, self.imap_config.MAIL_IMAP_PORT)
            self.mail.login(self.imap_config.MAIL_USER, self.imap_config.MAIL_PASSWORD)
            self._ensure_selected("INBOX")
            self.logger.info(f"IMAP: подключение и логин успешны ({self.imap_config.MAIL_IMAP_SERVER})")
        except Exception as e:
            self.logger.error(f"Ошибка подключения к IMAP: {e}")
            raise

    def _ensure_alive(self):
        try:
            self.mail.noop()
        except Exception:
            self.logger.warning("IMAP соединение не активно — переподключаюсь")
            self.connect()

    @staticmethod
    def return_mail_from(msg):
        addr = msg.get("from_email")
        if not addr and "from" in msg:
            match = re.search(r'<([^>]+)>', msg["from"])
            if match:
                addr = match.group(1)
            else:
                addr = email.utils.parseaddr(msg["from"])[1]
        else:
            addr = msg.get("From")
        return addr

    def mark_seen(self, uid: str):
        """
        Помечает письмо как прочитанное по UID.
        """
        try:
            self._ensure_selected("INBOX")
            typ, resp = self.mail.uid('STORE', uid, '+FLAGS', r'(\Seen)')
            if typ != "OK":
                self.logger.error(f"UID STORE \\Seen не применился: {resp}")
            else:
                self.logger.info(f"Письмо uid={uid} помечено как \\Seen")
        except Exception as e:
            self.logger.error(f"Ошибка при пометке \\Seen uid={uid}: {e}")

    def move_to_processed(self, uid: str, folder: str = "Processed"):
        """Перемещает письмо в папку Processed."""
        try:
            self._ensure_selected("INBOX")

            # копируем письмо в Processed
            status, _ = self.mail.uid("COPY", uid, folder)
            if status != "OK":
                self.logger.error(f"[IMAP] Не удалось скопировать UID={uid} в {folder}")
                return []
            # помечаем удалённым в INBOX и очищаем
            self.mail.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
            self.mail.expunge()
            self.logger.info(f"[IMAP] UID {uid}: перемещён в {folder}")
        except Exception as e:
            self.logger.error(f"[IMAP] Ошибка при переносе UID={uid}: {e}")

    def fetch_unseen_messages(self) -> list[dict]:
        """
        Возвращает список словарей по UNSEEN-письмам:
        { uid, from, subject, date, body, has_attachments, attachment_names }
        """
        mailbox = "INBOX"
        self._ensure_alive()
        self._ensure_selected(mailbox)

        status, data = self.mail.search(None, "UNSEEN")
        if status != "OK":
            return []

        ids = data[0].split()
        out: list[dict] = []

        for eid in ids:
            # UID письма
            _, uid_data = self.mail.fetch(eid, "(UID)")
            uid = uid_data[0].decode(errors="ignore").split()[-1].rstrip(")")

            res, msg_data = self.mail.fetch(eid, "(RFC822)")
            if res != "OK":
                continue

            msg = email.message_from_bytes(msg_data[0][1])

            subject = self._decode_header_value(msg.get("Subject"))
            from_ = self._decode_header_value(msg.get("From"))
            date_hdr = msg.get("Date")
            msg_id = msg.get('Message-ID') or msg.get('Message-Id')
            refs = msg.get('References')  # может быть None, это нормально

            try:
                date_iso = parsedate_to_datetime(date_hdr).isoformat()
            except Exception:
                date_iso = date_hdr or ""

            body, has_att, att_names = self._extract_text_and_attachments(msg)

            out.append({
                "eid": eid,
                "uid": uid,
                "from": from_,
                "subject": subject,
                "date": date_iso,
                "body": body,
                "has_attachments": has_att,
                "attachment_names": att_names,
                "message_id": msg_id,
                "references": refs
            })

        return out

    def reader_fn(self):
        """Функция-читатель (возвращает список писем) """
        items = self.fetch_unseen_messages()
        for it in items:
            uid = it["uid"]
            self.mark_seen(uid)
            self.move_to_processed(uid)
        return items
