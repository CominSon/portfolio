"""Сохранённые email работодателя (обратная связь / HR)."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def merge_contact_emails(primary: str, extra: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in [primary, *(extra or [])]:
        if not raw:
            continue
        e = normalize_email(str(raw))
        if e and e not in seen:
            seen.add(e)
            result.append(e)
    return result
