"""Ошибки tools для MCP."""

from typing import Any, Dict, Optional


def build_tool_error_payload(tool_name, message, error_type=None, hint=None, detail=None):
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
    return payload
