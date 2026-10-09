"""Входящая почта: POP3 SSL (pop.omega.sbrf.ru:995), как в Outlook."""

import email
import email.utils
import logging
import poplib
from typing import List, Optional, Tuple

from mail_mcp_agent.src.mail import mail_auth
from mail_mcp_agent.src.mail.message_body import (
    collect_attachments,
    decode_header_value,
    extract_body_text,
    extract_calendar_invites,
)
from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.mail.search_utils import query_matches
from mail_mcp_agent.src.utils.arg_coerce import coerce_int
from mail_mcp_agent.src.utils.safe_path import package_root

logger = logging.getLogger("mail_mcp.pop3")


def _decode_header_value(value):
    return decode_header_value(value)
def _connect():
    client, login, pwd_source = mail_auth.connect_pop3()
    client._mcp_login = login  # noqa: SLF001
    client._mcp_pwd_source = pwd_source
    return client


def _message_lines(client, msg_num, full=False):
    resp, lines, octets = client.top(msg_num, 0) if not full else client.retr(msg_num)
    resp_text = resp.decode("utf-8", errors="replace") if isinstance(resp, bytes) else str(resp)
    if not resp_text.startswith("+OK"):
        raise RuntimeError("POP3 ответ: {0}".format(resp_text))
    raw = b"\n".join(lines)
    return email.message_from_bytes(raw)


def _uidl_map(client):
    resp, items, _ = client.uidl()
    mapping = {}
    for item in items:
        text = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
        parts = text.split(None, 1)
        if len(parts) == 2:
            mapping[parts[0]] = parts[1]
    return mapping


def get_mailbox_stat():
    client = _connect()
    try:
        return client.stat()
    finally:
        try:
            client.quit()
        except Exception:
            pass


def list_folders():
    return {
        "protocol": "POP3",
        "folders": [{"name": "INBOX", "note": "POP3 — только входящие на сервере"}],
        "count": 1,
        "default_inbox_folder": "INBOX",
    }


def _message_numbers(client, limit=None):
    count, _ = client.stat()
    if count == 0:
        return []
    limit = coerce_int(limit, settings.LIST_MESSAGES_DEFAULT_LIMIT)
    limit = min(limit, settings.LIST_MESSAGES_MAX_LIMIT, count)
    start = max(1, count - limit + 1)
    return list(range(count, start - 1, -1))


def list_messages(folder="INBOX", limit=None, since_days=None):
    if folder and folder.upper() != "INBOX":
        raise ValueError("POP3 поддерживает только папку INBOX")

    client = _connect()
    try:
        uidl = _uidl_map(client)
        messages = []
        import datetime
        since = None
        since_days = coerce_int(since_days, None)
        if since_days:
            since = datetime.datetime.now() - datetime.timedelta(days=since_days)

        for num in _message_numbers(client, limit):
            msg = _message_lines(client, num, full=False)
            date_str = _decode_header_value(msg.get("Date"))
            if since and date_str:
                try:
                    dt = email.utils.parsedate_to_datetime(date_str)
                    if dt:
                        if getattr(dt, "tzinfo", None):
                            dt = dt.replace(tzinfo=None)
                        if dt < since:
                            continue
                except Exception:
                    pass
            messages.append({
                "uid": str(num),
                "uidl": uidl.get(str(num), ""),
                "folder": "INBOX",
                "subject": _decode_header_value(msg.get("Subject")),
                "from": _decode_header_value(msg.get("From")),
                "date": date_str,
            })
        return messages
    finally:
        try:
            client.quit()
        except Exception:
            pass


def _body_preview(msg):
    return extract_body_text(msg)
def search_messages(query, folder="INBOX", max_results=None):
    if folder and folder.upper() != "INBOX":
        raise ValueError("POP3: только INBOX")
    max_results = coerce_int(max_results, settings.SEARCH_MAX_RESULTS)
    scan_limit = min(settings.SEARCH_SCAN_MAX_MESSAGES, settings.LIST_MESSAGES_MAX_LIMIT)

    client = _connect()
    try:
        uidl = _uidl_map(client)
        results = []
        for num in _message_numbers(client, scan_limit):
            if len(results) >= max_results:
                break
            msg = _message_lines(client, num, full=True)
            subject = _decode_header_value(msg.get("Subject"))
            from_addr = _decode_header_value(msg.get("From"))
            to_addr = _decode_header_value(msg.get("To"))
            cc_addr = _decode_header_value(msg.get("Cc"))
            body_preview = _body_preview(msg)
            if query_matches(
                query,
                subject,
                from_addr,
                to_addr,
                cc_addr,
                body_preview,
            ):
                results.append({
                    "uid": str(num),
                    "uidl": uidl.get(str(num), ""),
                    "folder": "INBOX",
                    "subject": subject,
                    "from": from_addr,
                    "date": _decode_header_value(msg.get("Date")),
                    "body_preview": body_preview[: settings.SEARCH_BODY_PREVIEW_CHARS],
                })
        return results
    finally:
        try:
            client.quit()
        except Exception:
            pass


def _parse_attachments(msg, save_attachments):
    base = None
    if save_attachments:
        base = package_root(__file__) / settings.ATTACHMENTS_SUBDIR
        base.mkdir(parents=True, exist_ok=True)
    return collect_attachments(msg, save_attachments=save_attachments, save_dir=base)


def get_message(uid, folder="INBOX", save_attachments=False):
    if folder and folder.upper() != "INBOX":
        raise ValueError("POP3: только INBOX")
    try:
        msg_num = int(uid)
    except ValueError:
        raise ValueError("uid должен быть номером письма POP3 (1..N)")

    client = _connect()
    try:
        uidl = _uidl_map(client)
        msg = _message_lines(client, msg_num, full=True)
        body_text = _body_preview(msg)
        calendar_invites = extract_calendar_invites(msg)
        attachments = _parse_attachments(msg, save_attachments)
        return {
            "uid": str(msg_num),
            "uidl": uidl.get(str(msg_num), ""),
            "folder": "INBOX",
            "protocol": "POP3",
            "subject": _decode_header_value(msg.get("Subject")),
            "from": _decode_header_value(msg.get("From")),
            "to": _decode_header_value(msg.get("To")),
            "date": _decode_header_value(msg.get("Date")),
            "body_text": body_text,
            "calendar_invites": calendar_invites,
            "attachments": attachments,
        }
    finally:
        try:
            client.quit()
        except Exception:
            pass
