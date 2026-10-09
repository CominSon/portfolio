"""Форматирование ошибок tools для MCP-клиента."""

import re

from typing import Any, Dict, Optional


def short_db_message(exc):
    # type: (BaseException) -> str
    raw = str(exc).strip()
    m = re.search(
        r"(UndefinedColumn|UndefinedFunction|SyntaxError|InsufficientPrivilege|"
        r"QueryCanceled|permission denied|does not exist|operator does not exist)[^\n]*",
        raw,
        re.IGNORECASE,
    )
    if m:
        return m.group(0).strip()

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("LINE ") or not line:
            continue
        if "ERROR" in line or "Error" in line or "Undefined" in line:
            return line[:400]

    if len(raw) > 400:
        return raw[:400] + "..."
    return raw or type(exc).__name__


def build_tool_error_payload(
    tool_name,
    message,
    error_type=None,
    hint=None,
    detail=None,
    retry_meta=None,
):
    # type: (str, str, Optional[str], Optional[str], Optional[str], Optional[dict]) -> Dict[str, Any]
    payload = {
        "ok": False,
        "error": True,
        "tool": tool_name,
        "error_type": error_type or "ToolError",
        "message": message,
    }
    if hint:
        payload["hint"] = hint
    if detail and detail != message:
        payload["detail"] = detail[:2000] if len(detail) > 2000 else detail
    if retry_meta:
        if retry_meta.get("retry_recommended") is not None:
            payload["retry_recommended"] = retry_meta["retry_recommended"]
        if retry_meta.get("agent_retry"):
            payload["agent_retry"] = retry_meta["agent_retry"]
        if retry_meta.get("suggested_sql_note"):
            payload["suggested_sql_note"] = retry_meta["suggested_sql_note"]
    return payload
