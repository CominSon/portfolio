"""Нормализация хода AI: код в редактор, речь — в message и стенограмму."""
import re
from typing import Any

_CODE_FENCE = re.compile(r"```(?:[\w+-]+)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")


def _default_replace_range() -> dict[str, int]:
    return {"startLine": 1, "startColumn": 1, "endLine": 9999, "endColumn": 1}


def _strip_fences_from_message(message: str) -> tuple[str, list[str]]:
    blocks: list[str] = []

    def collect(match: re.Match[str]) -> str:
        body = (match.group(1) or "").strip()
        if body:
            blocks.append(body)
        return ""

    cleaned = _CODE_FENCE.sub(collect, message).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, blocks


def normalize_ai_turn(turn: dict[str, Any]) -> dict[str, Any]:
    """Вынести код из message в code_actions; оставить в message только речь."""
    message = (turn.get("message") or "").strip()
    code_actions: list[dict[str, Any]] = list(turn.get("code_actions") or [])

    cleaned, blocks = _strip_fences_from_message(message)
    if blocks:
        if not code_actions:
            code_actions.append(
                {
                    "action": "replace",
                    "range": _default_replace_range(),
                    "text": blocks[-1],
                }
            )
        message = cleaned

    if not code_actions:
        large_inline = [m.group(1) for m in _INLINE_CODE.finditer(message) if len(m.group(1)) > 80]
        if large_inline:
            code_actions.append(
                {
                    "action": "replace",
                    "range": _default_replace_range(),
                    "text": large_inline[-1],
                }
            )
            message = _INLINE_CODE.sub("", message).strip()
            message = re.sub(r"\n{3,}", "\n\n", message)

    if code_actions and not message.strip():
        message = (
            "Посмотрите код в редакторе. Что бы вы изменили в первую очередь — "
            "одним-двумя предложениями или правкой в редакторе?"
        )

    turn["message"] = message.strip()
    turn["code_actions"] = code_actions
    return turn
