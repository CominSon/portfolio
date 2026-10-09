"""Агрегация расписания запусков процедур из логов."""

from datetime import datetime

# datetime.weekday(): пн=0 … вс=6
_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def weekday_ru(dt):
    if not dt:
        return None
    return _WEEKDAY_RU[dt.weekday()]


def format_weekdays_ru(weekday_indices):
    """
    Индексы 0–6 → компактная русская метка: «пн–пт», «пн,ср,пт», «ежедн.».
    """
    days = sorted({int(i) for i in (weekday_indices or []) if 0 <= int(i) <= 6})
    if not days:
        return ""
    if days == list(range(7)):
        return "ежедн."
    if days == list(range(5)):
        return "пн–пт"
    # непрерывный диапазон
    if len(days) >= 2 and days[-1] - days[0] + 1 == len(days):
        return "{0}–{1}".format(_WEEKDAY_RU[days[0]], _WEEKDAY_RU[days[-1]])
    return ",".join(_WEEKDAY_RU[i] for i in days)


def format_schedule_edge_label(summary, max_len=36):
    """
    Подпись для стрелки SVG: «пн–пт 06:15» (типичный запуск), не дата last DONE.
    """
    if not isinstance(summary, dict):
        text = str(summary or "").strip()
        return text[:max_len] if text else ""

    # уже готовая метка
    ready = (summary.get("schedule_label") or summary.get("edge_label") or "").strip()
    if ready:
        return ready[:max_len]

    time_part = (
        summary.get("typical_start_time")
        or summary.get("typical_time")
        or ""
    )
    days_part = (
        summary.get("weekdays_ru_label")
        or format_weekdays_ru(summary.get("weekday_indices"))
        or ""
    )
    # weekdays могли прийти уже как ["пн","вт"]
    if not days_part and summary.get("weekdays"):
        wd = summary.get("weekdays") or []
        if wd and all(isinstance(x, str) and len(x) <= 3 for x in wd):
            # если английские Mon/Tue — смапим; если уже ru — склеим
            eng = {
                "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
                "пн": 0, "вт": 1, "ср": 2, "чт": 3, "пт": 4, "сб": 5, "вс": 6,
            }
            idxs = []
            for x in wd:
                idxs.append(eng.get(x.lower()[:3], eng.get(x.lower())))
            idxs = [i for i in idxs if i is not None]
            days_part = format_weekdays_ru(idxs) if idxs else ",".join(str(x) for x in wd)

    label = " ".join(p for p in (days_part, time_part) if p).strip()
    if label:
        return label[:max_len]

    # fallback только если типичного времени нет
    cadence = (summary.get("cadence") or "").strip()
    if cadence:
        return cadence[:max_len]
    return ""


def _parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    return None


def _median(values):
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    if len(s) % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def summarize_procedure_schedule(rows):
    """
    Медиана времени старта, длительности, дни недели (ru), последний запуск.
    schedule_label — готовая подпись для схемы: «пн–пт 06:15».
    """
    starts = []
    durations = []
    end_durations = []
    weekday_indices = set()
    last_run = None
    last_status = None
    last_end = None

    for row in rows or []:
        ds = _parse_ts(row.get("date_start"))
        de = _parse_ts(row.get("date_end"))
        if ds:
            starts.append(ds.hour * 3600 + ds.minute * 60 + ds.second)
            weekday_indices.add(ds.weekday())
            if last_run is None or ds > last_run:
                last_run = ds
                last_end = de
                last_status = row.get("status")
        if ds and de and de >= ds:
            durations.append((de - ds).total_seconds())
            end_durations.append(de.hour * 3600 + de.minute * 60 + de.second)

    med_start = _median(starts)
    med_dur = _median(durations)

    typical_start = None
    if med_start is not None:
        h = int(med_start // 3600)
        m = int((med_start % 3600) // 60)
        typical_start = "{0:02d}:{1:02d}".format(h, m)

    days_since = None
    inactive = False
    if last_run:
        days_since = (datetime.now() - last_run).days
        inactive = days_since > 30

    med_end = _median(end_durations)
    typical_end = None
    if med_start is not None and med_dur is not None:
        total = int(med_start + med_dur)
        h = (total // 3600) % 24
        m = (total % 3600) // 60
        typical_end = "{0:02d}:{1:02d}".format(h, m)
    elif med_end is not None:
        h = int(med_end // 3600)
        m = (med_end % 3600) // 60
        typical_end = "{0:02d}:{1:02d}".format(h, m)

    wd_sorted = sorted(weekday_indices)
    weekdays_ru = [_WEEKDAY_RU[i] for i in wd_sorted]
    weekdays_ru_label = format_weekdays_ru(wd_sorted)

    summary = {
        "run_count": len(rows or []),
        "typical_start_time": typical_start,
        "typical_end_time": typical_end,
        "median_duration_sec": int(med_dur) if med_dur is not None else None,
        "weekday_indices": wd_sorted,
        "weekdays": weekdays_ru,
        "weekdays_ru_label": weekdays_ru_label,
        "last_run_at": last_run.strftime("%Y-%m-%d %H:%M") if last_run else None,
        "last_run_end_at": last_end.strftime("%Y-%m-%d %H:%M") if last_end else None,
        "last_status": last_status,
        "days_since_last_run": days_since,
        "inactive": inactive,
    }
    summary["schedule_label"] = format_schedule_edge_label(summary)
    return summary
