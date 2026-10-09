"""Разрешение ФИО → email — как «Проверить имена» в Outlook."""

import logging
import re
import sys

logger = logging.getLogger("mail_mcp.address_book")


def resolve_recipients(query, max_results=20):
    query = (query or "").strip()
    if not query:
        raise ValueError("Укажите ФИО или часть имени для поиска")

    if sys.platform == "win32":
        outlook_results = _resolve_via_outlook(query, max_results)
        if outlook_results is not None:
            return outlook_results

    return {
        "ok": False,
        "query": query,
        "contacts": [],
        "message": "Адресная книга Outlook недоступна на этой машине.",
        "hint": "Укажите email явно или откройте Outlook.",
    }


def _name_variants(query):
    parts = [p for p in re.split(r"[\s,]+", query) if p]
    variants = [query]
    if len(parts) >= 2:
        variants.extend([
            "{0} {1}".format(parts[0], parts[1]),
            "{0} {1}".format(parts[1], parts[0]),
            "{0}, {1}".format(parts[0], parts[1]),
            "{0}, {1}".format(parts[1], parts[0]),
        ])
    seen = set()
    result = []
    for item in variants:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _words_in_name(query, name):
    words = [w.lower() for w in re.split(r"[\s,]+", query) if len(w) >= 2]
    if not words:
        return query.lower() in (name or "").lower()
    name_lower = (name or "").lower()
    return all(word in name_lower for word in words)


def _resolve_via_outlook(query, max_results):
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError:
        return None

    outlook = None
    try:
        pythoncom.CoInitialize()
        try:
            outlook = win32com.client.GetActiveObject("Outlook.Application")
        except Exception:
            outlook = win32com.client.Dispatch("Outlook.Application")

        session = outlook.Session
        contacts = []

        for variant in _name_variants(query):
            _collect_from_recipient(session, variant, contacts, max_results)
            if len(contacts) >= max_results:
                break

        if len(contacts) < max_results:
            _collect_from_gal(session, query, contacts, max_results)

        if len(contacts) < max_results:
            _collect_from_address_lists(session, query, contacts, max_results)

        contacts = contacts[:max_results]
        if not contacts:
            return {
                "ok": False,
                "query": query,
                "contacts": [],
                "message": (
                    "В адресной книге Outlook не найдено совпадений для «{0}». "
                    "Проверьте написание или укажите email.".format(query)
                ),
                "hint": "Outlook должен быть запущен. Попробуйте «Фамилия Имя» как в поле «Кому».",
            }

        return {
            "ok": True,
            "query": query,
            "contacts": contacts,
            "ambiguous": len(contacts) > 1,
            "message": (
                "Найдено контактов: {0}. При ambiguous=true уточните to перед send_email.".format(
                    len(contacts)
                )
            ),
        }
    except Exception as exc:
        logger.warning("Outlook resolve failed: %s", exc)
        return {
            "ok": False,
            "query": query,
            "contacts": [],
            "message": "Outlook: {0}".format(exc),
            "hint": "Запустите Outlook и повторите запрос.",
        }
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _collect_from_recipient(session, display_name, contacts, max_results):
    try:
        recipient = session.CreateRecipient(display_name)
        recipient.Resolve()
        if recipient.Resolved:
            contact = _recipient_to_contact(recipient)
            if contact and not _contact_exists(contacts, contact):
                contacts.append(contact)
    except Exception as exc:
        logger.debug("CreateRecipient %s: %s", display_name, exc)


def _collect_from_gal(session, query, contacts, max_results):
    try:
        gal = session.GetGlobalAddressList()
        entries = gal.AddressEntries
        total = int(entries.Count)
    except Exception as exc:
        logger.debug("GAL open: %s", exc)
        return

    first_word = (re.split(r"[\s,]+", query) or [""])[0].lower()
    for i in range(1, total + 1):
        if len(contacts) >= max_results:
            return
        try:
            entry = entries.Item(i)
        except Exception:
            continue
        name = entry.Name or ""
        if first_word and first_word not in name.lower():
            continue
        if not _words_in_name(query, name):
            continue
        contact = _entry_to_contact(entry)
        if contact and not _contact_exists(contacts, contact):
            contacts.append(contact)


def _collect_from_address_lists(session, query, contacts, max_results):
    try:
        for addr_list in session.AddressLists:
            try:
                entries = addr_list.AddressEntries
                total = int(entries.Count)
            except Exception:
                continue
            for i in range(1, total + 1):
                if len(contacts) >= max_results:
                    return
                try:
                    entry = entries.Item(i)
                except Exception:
                    continue
                name = entry.Name or ""
                if not _words_in_name(query, name):
                    continue
                contact = _entry_to_contact(entry)
                if contact and not _contact_exists(contacts, contact):
                    contacts.append(contact)
    except Exception as exc:
        logger.debug("AddressLists: %s", exc)


def _recipient_to_contact(recipient):
    try:
        if recipient.AddressEntry:
            return _entry_to_contact(recipient.AddressEntry)
        addr = (recipient.Address or "").strip().replace("SMTP:", "").strip()
        if addr and "@" in addr:
            return {"display_name": recipient.Name or addr, "email": addr}
    except Exception:
        pass
    return None


def _contact_exists(contacts, candidate):
    email = (candidate.get("email") or "").lower()
    for item in contacts:
        if (item.get("email") or "").lower() == email:
            return True
    return False


def _entry_to_contact(entry):
    try:
        name = entry.Name or ""
        if hasattr(entry, "GetExchangeUser"):
            user = entry.GetExchangeUser()
            if user and user.PrimarySmtpAddress:
                return {
                    "display_name": name or user.Name,
                    "email": user.PrimarySmtpAddress.strip(),
                    "organization": getattr(user, "CompanyName", None),
                    "department": getattr(user, "Department", None),
                }
        addr = (entry.Address or "").strip().replace("SMTP:", "").strip()
        if not addr and hasattr(entry, "PropertyAccessor"):
            try:
                addr = entry.PropertyAccessor.GetProperty(
                    "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                )
            except Exception:
                pass
        if not addr or "@" not in addr:
            return None
        return {
            "display_name": name,
            "email": addr.strip(),
        }
    except Exception:
        return None
