"""Единый табличный отчёт по сессиям pg_stat_activity / manage_backend."""

# state обязателен и идёт сразу после pid
SESSION_TABLE_COLUMNS = [
    "pid",
    "state",
    "usename",
    "datname",
    "query_start",
    "xact_start",
    "application_name",
    "client_addr",
    "wait_event_type",
    "wait_event",
    "query",
]


def normalize_session_row(row):
    # type: (dict) -> dict
    out = {}
    for col in SESSION_TABLE_COLUMNS:
        if col in row:
            out[col] = row[col]
        elif col == "state" and "status" in row:
            out[col] = row["status"]
        else:
            out[col] = None
    if out.get("query") is None:
        for key in ("current_query", "query_text"):
            if key in row:
                out["query"] = row[key]
                break
    if out.get("state") is None:
        out["state"] = "unknown"
    return out


def build_session_report(scope_key, scope_label, username, rows, source):
    # type: (str, str, str, list, str) -> dict
    normalized = [normalize_session_row(r) for r in rows]
    return {
        "scope": scope_key,
        "scope_label": scope_label,
        "username": username,
        "source": source,
        "columns": SESSION_TABLE_COLUMNS,
        "sessions_table": normalized,
        "count": len(normalized),
        "status_legend": {
            "active": "выполняет запрос сейчас",
            "idle": "ожидает клиента",
            "idle in transaction": "транзакция открыта, запрос не выполняется",
            "waiting": "ожидает ресурс (GP)",
        },
    }
