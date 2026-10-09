"""Подсказки при ошибках БД и политика повторных попыток для агента."""

import re

AGENT_MAX_RETRIES = 3


def analyze_db_error(tool_name, exc):
    msg = str(exc)
    lower = msg.lower()
    hint = None
    suggested_sql_note = None

    if "wait_event_type" in lower or "wait_event" in lower:
        hint = (
            "Используйте tool list_sessions(scope=self), а не run_select по pg_stat_activity. "
            "На этом Greenplum нет колонок wait_event_*."
        )

    elif "undefinedfunction" in lower or "operator does not exist" in lower:
        if "@?" in msg or "jsonpath" in lower or ("jsonb" in lower and "?" in msg):
            suggested_sql_note = (
                "Greenplum не поддерживает JSON path оператор @? (SQL/JSON). "
                "Вместо этого:\n"
                "- (col::json->>'key') для одного поля\n"
                "- jsonb_array_elements(col::jsonb) для массива\n"
                "- col::jsonb ? 'key' — проверка наличия ключа (если доступно)\n"
                "- regexp или substring для простого поиска в тексте"
            )
            hint = (
                "Перепишите SQL без @? и повторите run_select. "
                "Сначала покажите пользователю исправленный запрос, если он сложный."
            )
        elif "jsonb" in lower:
            hint = "Проверьте синтаксис JSON: ->, ->>, ::jsonb. Перепишите SQL и повторите."

    elif "undefinedcolumn" in lower or "does not exist" in lower:
        hint = "Колонка или объект не найдены. Проверьте get_columns / search_tables и исправьте SQL."

    elif "syntaxerror" in lower:
        hint = "Синтаксическая ошибка SQL. Упростите запрос и повторите."

    elif "statement timeout" in lower or "querycanceled" in lower:
        hint = "Таймаут. Добавьте LIMIT, сузьте фильтр или используйте export_query_csv."
        return _payload(tool_name, hint, suggested_sql_note, retry=False)

    elif tool_name == "run_select" and "relowner" in lower:
        hint = "Для объектов по владельцу — list_owned_objects, не run_select."

    elif tool_name == "run_select":
        hint = "Исправьте SQL с учётом message и detail, затем повторите run_select."

    return _payload(tool_name, hint, suggested_sql_note, retry=True)


def _payload(tool_name, hint, suggested_sql_note, retry=True):
    body = {
        "retry_recommended": retry,
        "agent_retry": {
            "max_attempts": AGENT_MAX_RETRIES,
            "instruction": (
                "Ошибка возвращена для исправления. "
                "Проанализируйте message, hint и detail. "
                "Исправьте SQL или параметры и вызовите {0} снова. "
                "Максимум {1} попыток исправления подряд.".format(
                    tool_name, AGENT_MAX_RETRIES
                )
            ),
        },
    }
    if hint:
        body["hint"] = hint
    if suggested_sql_note:
        body["suggested_sql_note"] = suggested_sql_note
    return body


def enrich_error_payload(payload, tool_name, exc):
    analysis = analyze_db_error(tool_name, exc)
    payload["retry_recommended"] = analysis.get("retry_recommended", False)
    if analysis.get("agent_retry"):
        payload["agent_retry"] = analysis["agent_retry"]
    if analysis.get("hint") and not payload.get("hint"):
        payload["hint"] = analysis["hint"]
    elif analysis.get("hint"):
        payload["hint"] = payload["hint"] + " " + analysis["hint"]
    if analysis.get("suggested_sql_note"):
        payload["suggested_sql_note"] = analysis["suggested_sql_note"]
    return payload
