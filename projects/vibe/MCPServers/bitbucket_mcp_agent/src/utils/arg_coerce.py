"""Приведение аргументов tools (GigaCode иногда шлёт строки / {content: ...})."""


def _unwrap_value(value):
    """GigaCode иногда оборачивает скаляры в {content: \"...\"}."""
    if isinstance(value, dict):
        if "content" in value and len(value) <= 3:
            return _unwrap_value(value.get("content"))
        if "text" in value and len(value) <= 3:
            return _unwrap_value(value.get("text"))
    return value


def normalize_tool_arguments(arguments):
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return {k: _unwrap_value(v) for k, v in arguments.items()}
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            import json
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {k: _unwrap_value(v) for k, v in parsed.items()}
        except ValueError:
            pass
        return {}
    return {}
