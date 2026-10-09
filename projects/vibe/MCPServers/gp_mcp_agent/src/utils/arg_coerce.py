"""Приведение аргументов tools (GigaCode иногда шлёт строки)."""

from mcp_workspace_config.arg_aliases import normalize_gp_arguments


def normalize_tool_arguments(arguments):
    if arguments is None:
        return {}
    if isinstance(arguments, dict):
        return normalize_gp_arguments(arguments)
    if isinstance(arguments, str):
        text = arguments.strip()
        if not text:
            return {}
        try:
            import json
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return normalize_gp_arguments(parsed)
        except ValueError:
            pass
        return {}
    return {}


def coerce_int(value, default=None):
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return default
