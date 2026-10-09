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
        payload["detail"] = detail[:2000]
    return payload
