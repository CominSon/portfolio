from datetime import datetime, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def format_moscow(dt: datetime | None) -> str:
    """Человекочитаемое время в московском поясе для отчётов и писем."""
    utc = ensure_utc(dt)
    if utc is None:
        return ""
    return utc.astimezone(MSK).strftime("%Y-%m-%d %H:%M:%S MSK")
