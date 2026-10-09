"""Единая таблица порядка запуска и сортировка по типичному времени."""

from report_mcp_agent.src.report.pxf_rules import pxf_lookup_name

try:
    from gp_mcp_agent.src.utils.procedure_schedule import format_schedule_edge_label
except Exception:
    format_schedule_edge_label = None


def collect_schedule_entries(data):
    """Собрать entries без дублей по (kind, object); подтянуть из lineage_steps."""
    by_key = {}
    for e in data.get("schedule_entries") or []:
        obj = (e.get("object") or "").strip()
        if not obj:
            continue
        kind = (e.get("kind") or "procedure").strip()
        key = (kind, obj)
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = dict(e)
        else:
            # слияние: не терять schedule_label / note / summary
            merged = dict(prev)
            for k, v in e.items():
                if v is None or v == "" or v == "—":
                    continue
                if k == "target" and merged.get("target"):
                    continue
                if k == "summary" and isinstance(v, dict) and isinstance(
                    merged.get("summary"), dict
                ):
                    s = dict(merged["summary"])
                    s.update(v)
                    merged["summary"] = s
                else:
                    merged[k] = v
            by_key[key] = merged

    for step in data.get("lineage_steps") or []:
        proc = (step.get("procedure") or "").strip()
        sched = step.get("schedule") or {}
        if not proc or not sched:
            continue
        key = ("procedure", proc)
        if key not in by_key:
            by_key[key] = {
                "kind": "procedure",
                "object": proc,
                "summary": sched.get("summary") or sched,
                "note": step.get("notes"),
            }
        elif not by_key[key].get("summary"):
            by_key[key]["summary"] = sched.get("summary") or sched

    return list(by_key.values())


def entry_schedule_label(entry):
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
    merged = dict(summary)
    for k in (
        "typical_start_time",
        "typical_time",
        "weekdays",
        "weekdays_ru_label",
        "weekday_indices",
        "schedule_label",
        "cadence",
    ):
        if entry.get(k) is not None and k not in merged:
            merged[k] = entry.get(k)
    if entry.get("schedule_label"):
        return str(entry["schedule_label"])
    if format_schedule_edge_label is not None:
        label = format_schedule_edge_label(merged, max_len=48)
        if label and label.lower() not in ("daily", "weekly"):
            return label
        if label and merged.get("typical_start_time"):
            return label
    days = merged.get("weekdays_ru_label") or ""
    time_part = merged.get("typical_start_time") or merged.get("typical_time") or ""
    if days or time_part:
        return ("{0} {1}".format(days, time_part)).strip()
    cadence = (merged.get("cadence") or entry.get("cadence") or "").strip()
    if cadence:
        return cadence
    if entry.get("last_success"):
        return "посл. {0}".format(entry["last_success"])
    return ""


def _sort_key(entry):
    """Для сортировки по времени запуска: минуты от полуночи, неизвестные — в конец."""
    summary = entry.get("summary") if isinstance(entry.get("summary"), dict) else {}
    t = (
        summary.get("typical_start_time")
        or summary.get("typical_time")
        or ""
    )
    label = entry_schedule_label(entry)
    # вытащить HH:MM из label
    import re
    m = re.search(r"(\d{1,2}):(\d{2})", t or label or "")
    if m:
        return (0, int(m.group(1)) * 60 + int(m.group(2)), entry.get("object") or "")
    return (1, 9999, entry.get("object") or "")


def kind_ru(kind):
    return {
        "procedure": "процедура",
        "pxf": "PXF",
        "pcopy": "p_copy",
        "view": "view",
    }.get(kind or "procedure", kind or "—")


def split_found_and_missing(entries):
    found, missing = [], []
    for e in entries:
        label = entry_schedule_label(e)
        summary = e.get("summary") if isinstance(e.get("summary"), dict) else {}
        has_time = bool(
            summary.get("typical_start_time")
            or summary.get("typical_time")
            or (label and ":" in label)
        )
        has_log = has_time or bool(e.get("last_success")) or bool(
            summary.get("run_count")
        )
        # голое daily без времени — считаем «слабым», в основную таблицу с пометкой
        if has_log or label:
            found.append(e)
        else:
            missing.append(e)
    found.sort(key=_sort_key)
    missing.sort(key=lambda e: (e.get("object") or ""))
    return found, missing


def format_run_order_section(data):
    """§5: одна таблица по порядку запуска + отдельно без логов."""
    entries = collect_schedule_entries(data)
    found, missing = split_found_and_missing(entries)

    parts = [
        "## 5. Порядок запуска",
        "",
        "Сортировка по типичному времени запуска (день + время). "
        "Одна строка на объект — без дублей и без колонки «целевая таблица».",
        "",
        "### 5.1. Найдены в логах / с известным расписанием",
        "",
        "| # | Объект | Тип | Расписание | Примечание |",
        "|---|--------|-----|------------|------------|",
    ]
    if found:
        for i, e in enumerate(found, 1):
            obj = e.get("object") or "—"
            note = e.get("note") or "—"
            if e.get("kind") == "pxf":
                pxf = e.get("pxf_table_name") or pxf_lookup_name(obj)
                if note == "—":
                    note = "PXF table_name=`{0}`".format(pxf)
            parts.append(
                "| {0} | `{1}` | {2} | {3} | {4} |".format(
                    i,
                    obj,
                    kind_ru(e.get("kind")),
                    entry_schedule_label(e) or "—",
                    note,
                )
            )
    else:
        parts.append(
            "| — | — | — | _заполните upsert_schedule_entry "
            "(schedule_label из get_procedure_schedule)_ | — |"
        )

    parts.extend([
        "",
        "### 5.2. Не найдены в логах запусков",
        "",
        "| Объект | Тип | Примечание |",
        "|--------|-----|------------|",
    ])
    if missing:
        for e in missing:
            parts.append(
                "| `{0}` | {1} | {2} |".format(
                    e.get("object") or "—",
                    kind_ru(e.get("kind")),
                    e.get("note") or "нет записей в logs_procedure / logs_pxf",
                )
            )
    else:
        parts.append("| — | — | _все объекты из §5.1 имеют расписание_ |")

    parts.append("")
    return "\n".join(parts)
