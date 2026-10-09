"""Форматирование записей стенограммы."""
from __future__ import annotations

import re
from typing import Any

_CODE_CONTEXT_MARKERS = re.compile(
    r"код|редактор|функци|алгоритм|запрос|sql|скрипт|исправ|оптимиз|реализ|"
    r"напиш|проанализ|что выведет|баг|ошибк|рефактор|класс|метод|переменн|"
    r"цикл|массив|список|словар|таблиц|join|where|select|индекс|тип данных|"
    r"разбер|review|ревью|сниппет|фрагмент",
    re.I,
)

_BEHAVIORAL_MARKERS = re.compile(
    r"кейс из практики|нетривиальн|почему выбрали|расскажите о себе|"
    r"ваш опыт в целом|soft skill|командн",
    re.I,
)


def question_needs_editor_code(ai_text: str, *, format_name: str = "") -> bool:
    """Вопрос предполагает анализ кода в редакторе."""
    if not (ai_text or "").strip():
        return False
    text = ai_text.strip()
    if _BEHAVIORAL_MARKERS.search(text) and not _CODE_CONTEXT_MARKERS.search(text):
        return False
    fmt = (format_name or "").lower()
    if "architecture" in fmt and not _CODE_CONTEXT_MARKERS.search(text):
        return False
    if "code review" in fmt or "live coding" in fmt:
        return bool(_CODE_CONTEXT_MARKERS.search(text))
    return bool(_CODE_CONTEXT_MARKERS.search(text))


def code_from_actions(code_actions: list[dict[str, Any]] | None) -> str:
    if not code_actions:
        return ""
    for action in code_actions:
        if not isinstance(action, dict):
            continue
        if action.get("action") == "replace":
            text = str(action.get("text") or "").strip()
            if text:
                return text
    for action in code_actions:
        if not isinstance(action, dict):
            continue
        text = str(action.get("text") or "").strip()
        if text:
            return text
    return ""


def ai_transcript_with_editor_code(
    ai_text: str,
    editor_content: str | None,
    *,
    format_name: str = "",
    code_actions: list[dict[str, Any]] | None = None,
) -> str:
    """Добавить снимок редактора в стенограмму после вопроса AI."""
    text = (ai_text or "").strip()
    code = (editor_content or "").strip() or code_from_actions(code_actions)
    if not text or not code:
        return text
    if "[Код в редакторе]" in text:
        return text
    if not question_needs_editor_code(text, format_name=format_name):
        return text
    return f"{text}\n\n[Код в редакторе]\n{code}"


def should_clear_editor_after_turn(
    ai_text: str,
    *,
    code_actions_applied: int,
    format_name: str = "",
) -> bool:
    """Сбросить редактор, если новый вопрос не про код в редакторе."""
    if code_actions_applied > 0:
        return False
    if question_needs_editor_code(ai_text, format_name=format_name):
        return False
    return True
