"""Извлечение текста и календарных приглашений из MIME."""

import re
from email.header import decode_header


def decode_header_value(value):
    if not value:
        return ""
    parts = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts).strip()


def _decode_part(part):
    payload = part.get_payload(decode=True)
    if not payload:
        return ""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")


def _strip_html(html_text):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html_text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_body_text(msg):
    plain_parts = []
    html_parts = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = (part.get_content_type() or "").lower()
            disposition = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disposition and content_type != "text/calendar":
                continue
            if content_type == "text/plain":
                text = _decode_part(part)
                if text:
                    plain_parts.append(text)
            elif content_type == "text/html":
                text = _decode_part(part)
                if text:
                    html_parts.append(_strip_html(text))
    else:
        content_type = (msg.get_content_type() or "").lower()
        text = _decode_part(msg)
        if content_type == "text/html":
            return _strip_html(text)
        return text

    if plain_parts:
        return "\n\n".join(plain_parts).strip()
    if html_parts:
        return "\n\n".join(html_parts).strip()
    return ""


def _unfold_ics_line(line):
    return line.replace("\\n", "\n").replace("\\,", ",").strip()


def parse_ics_text(ics_text):
    events = []
    if not ics_text:
        return events

    current = {}
    for raw_line in ics_text.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                events.append(current)
            current = {}
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.split(";", 1)[0].upper()
        value = _unfold_ics_line(value)
        if key in ("SUMMARY", "DESCRIPTION", "LOCATION", "DTSTART", "DTEND", "ORGANIZER", "UID"):
            current[key.lower()] = value

    return events


def extract_calendar_invites(msg):
    invites = []
    if not msg.is_multipart():
        return invites

    for part in msg.walk():
        content_type = (part.get_content_type() or "").lower()
        filename = decode_header_value(part.get_filename() or "")
        is_calendar = (
            content_type == "text/calendar"
            or filename.lower().endswith(".ics")
        )
        if not is_calendar:
            continue
        ics_text = _decode_part(part)
        events = parse_ics_text(ics_text)
        for event in events:
            event["source_filename"] = filename or None
            invites.append(event)
    return invites


def collect_attachments(msg, save_attachments=False, save_dir=None):
    attachments = []
    if not msg.is_multipart():
        return attachments

    for part in msg.walk():
        filename = part.get_filename()
        content_type = (part.get_content_type() or "").lower()
        disposition = (part.get("Content-Disposition") or "").lower()

        if content_type.startswith("multipart/"):
            continue

        is_attachment = "attachment" in disposition
        is_named_inline = filename and content_type not in ("text/plain", "text/html")
        is_calendar = content_type == "text/calendar" or (
            filename and filename.lower().endswith(".ics")
        )

        if not (is_attachment or is_named_inline or is_calendar):
            continue

        filename = decode_header_value(filename) or (
            "invite.ics" if is_calendar else "attachment.bin"
        )
        info = {"filename": filename, "content_type": content_type}

        if is_calendar:
            ics_text = _decode_part(part)
            events = parse_ics_text(ics_text)
            if events:
                info["calendar_events"] = events

        if save_attachments and save_dir is not None:
            safe_name = re.sub(r'[<>:"/\\|?*]', "_", filename) or "attachment.bin"
            path = save_dir / safe_name
            payload = part.get_payload(decode=True) or b""
            path.write_bytes(payload)
            info["saved_path"] = str(path)

        attachments.append(info)
    return attachments
