"""Формат ошибок tool для MCP."""


def tool_error(message, hint=None, retry_recommended=False, detail=None):
    out = {
        "ok": False,
        "error": True,
        "message": message,
        "retry_recommended": bool(retry_recommended),
    }
    if hint:
        out["hint"] = hint
    if detail is not None:
        out["detail"] = detail
    return out
