"""IMAP: папки, список писем, поиск, чтение."""

import email
import imaplib
import logging
import re
from email.header import decode_header
from typing import Any, List, Optional, Tuple

from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.auth import noterball_auth
from mail_mcp_agent.src.utils.safe_path import package_root

logger = logging.getLogger("mail_mcp.imap")

_inbox_folder_cache = None


def _decode_header_value(value):
    if not value:
        return ""
    parts = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts).strip()


def _imap_login_candidates():
    return noterball_auth.get_imap_smtp_login_candidates()


def _connect():
    password = noterball_auth.get_password_from_noterball()
    last_error = None
    for login in _imap_login_candidates():
        try:
            client = imaplib.IMAP4_SSL(settings.IMAP_HOST, settings.IMAP_PORT)
            client.login(login, password)
            logger.info("IMAP login OK as %s", login)
            return client
        except Exception as exc:
            last_error = exc
            logger.debug("IMAP login failed for %s: %s", login, exc)
    raise RuntimeError(
        "IMAP авторизация не удалась ({0}:{1}). Последняя ошибка: {2}. "
        "Проверьте set_my_email и доступ к {0} из корпоративной сети.".format(
            settings.IMAP_HOST, settings.IMAP_PORT, last_error
        )
    )


def _resolve_inbox_folder(client):
    global _inbox_folder_cache
    if _inbox_folder_cache:
        return _inbox_folder_cache

    configured = (settings.IMAP_INBOX_FOLDER or "").strip()
    if configured:
        _inbox_folder_cache = configured
        return configured

    status, data = client.list()
    if status != "OK":
        _inbox_folder_cache = "INBOX"
        return "INBOX"

    names = []
    for item in data or []:
        raw = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
        name = _parse_folder_name(raw)
        if name:
            names.append(name)

    for name in names:
        lower = name.lower()
        if lower == "inbox" or lower.startswith("inbox."):
            _inbox_folder_cache = name
            return name

    _inbox_folder_cache = "INBOX"
    return "INBOX"


def _normalize_folder(folder):
    if not folder or folder.upper() == "INBOX":
        client = _connect()
        try:
            return _resolve_inbox_folder(client)
        finally:
            try:
                client.logout()
            except Exception:
                pass
    return folder


def list_folders():
    client = _connect()
    try:
        status, data = client.list()
        if status != "OK":
            raise RuntimeError("IMAP LIST failed: {0}".format(status))
        folders = []
        for item in data or []:
            if not item:
                continue
            raw = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
            name = _parse_folder_name(raw)
            if name:
                folders.append({"name": name, "raw": raw})
        inbox = _resolve_inbox_folder(client)
        return {
            "folders": folders,
            "count": len(folders),
            "default_inbox_folder": inbox,
        }
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _parse_folder_name(list_line):
    m = re.search(r'"([^"]+)"\s*$', list_line)
    if m:
        return m.group(1)
    parts = list_line.rsplit(" ", 1)
    return parts[-1].strip('"') if parts else list_line


def list_messages(folder="INBOX", limit=None, since_days=None):
    limit = limit or settings.LIST_MESSAGES_DEFAULT_LIMIT
    limit = min(limit, settings.LIST_MESSAGES_MAX_LIMIT)
    folder = _normalize_folder(folder)

    client = _connect()
    try:
        client.select(folder, readonly=True)
        criteria = "ALL"
        if since_days:
            import datetime
            since = datetime.date.today() - datetime.timedelta(days=since_days)
            criteria = '(SINCE "{0}")'.format(since.strftime("%d-%b-%Y"))

        status, data = client.search(None, criteria)
        if status != "OK":
            raise RuntimeError("IMAP SEARCH failed")

        ids = (data[0] or b"").split()
        ids = ids[-limit:] if len(ids) > limit else ids
        ids.reverse()

        messages = []
        for msg_id in ids:
            status, msg_data = client.fetch(msg_id, "(RFC822.HEADER FLAGS)")
            if status != "OK" or not msg_data:
                continue
            header_bytes = _extract_fetch_bytes(msg_data)
            if not header_bytes:
                continue
            msg = email.message_from_bytes(header_bytes)
            messages.append({
                "uid": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                "folder": folder,
                "subject": _decode_header_value(msg.get("Subject")),
                "from": _decode_header_value(msg.get("From")),
                "date": _decode_header_value(msg.get("Date")),
            })
        return messages
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _extract_fetch_bytes(msg_data):
    for part in msg_data:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1]
    return None


def search_messages(query, folder="INBOX", max_results=None):
    max_results = max_results or settings.SEARCH_MAX_RESULTS
    query_lower = query.lower().strip()
    folder = _normalize_folder(folder)

    client = _connect()
    try:
        client.select(folder, readonly=True)
        status, data = client.search(None, "ALL")
        if status != "OK":
            raise RuntimeError("IMAP SEARCH failed")

        ids = (data[0] or b"").split()
        ids.reverse()
        results = []

        for msg_id in ids:
            if len(results) >= max_results:
                break
            status, msg_data = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not msg_data:
                continue
            raw = _extract_fetch_bytes(msg_data)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            subject = _decode_header_value(msg.get("Subject"))
            from_addr = _decode_header_value(msg.get("From"))
            body_preview = _extract_body_preview(msg)
            haystack = " ".join([subject, from_addr, body_preview]).lower()
            if query_lower in haystack:
                results.append({
                    "uid": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                    "folder": folder,
                    "subject": subject,
                    "from": from_addr,
                    "date": _decode_header_value(msg.get("Date")),
                    "body_preview": body_preview[: settings.SEARCH_BODY_PREVIEW_CHARS],
                })
        return results
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _extract_body_preview(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def get_message(uid, folder="INBOX", save_attachments=False):
    folder = _normalize_folder(folder)
    client = _connect()
    try:
        client.select(folder, readonly=True)
        status, msg_data = client.fetch(
            uid.encode() if isinstance(uid, str) else uid, "(RFC822)"
        )
        if status != "OK" or not msg_data:
            raise ValueError("Письмо uid={0} не найдено в {1}".format(uid, folder))

        raw = _extract_fetch_bytes(msg_data)
        if not raw:
            raise ValueError("Пустой ответ IMAP для uid={0}".format(uid))

        msg = email.message_from_bytes(raw)
        body_text, attachments = _parse_full_message(msg, save_attachments)
        return {
            "uid": str(uid),
            "folder": folder,
            "subject": _decode_header_value(msg.get("Subject")),
            "from": _decode_header_value(msg.get("From")),
            "to": _decode_header_value(msg.get("To")),
            "date": _decode_header_value(msg.get("Date")),
            "body_text": body_text,
            "attachments": attachments,
        }
    finally:
        try:
            client.logout()
        except Exception:
            pass


def _parse_full_message(msg, save_attachments):
    from pathlib import Path

    body_parts = []
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            filename = part.get_filename()
            if filename:
                filename = _decode_header_value(filename)
                info = {"filename": filename, "content_type": part.get_content_type()}
                if save_attachments:
                    path = _save_attachment_part(part, filename)
                    info["saved_path"] = str(path)
                attachments.append(info)
                continue
            if part.get_content_type() == "text/plain" and "attachment" not in disposition.lower():
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body_parts.append(payload.decode(charset, errors="replace"))
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body_parts.append(payload.decode(charset, errors="replace"))

    return "\n".join(body_parts), attachments


def _save_attachment_part(part, filename):
    from pathlib import Path

    base = package_root(__file__) / settings.ATTACHMENTS_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[<>:"/\\|?*]', "_", filename) or "attachment.bin"
    path = base / safe_name
    payload = part.get_payload(decode=True) or b""
    path.write_bytes(payload)
    return path
