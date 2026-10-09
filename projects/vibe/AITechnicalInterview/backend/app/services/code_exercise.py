"""Кодовое задание в редакторе: базовая версия от AI и сравнение с ответом кандидата."""
import difflib
from typing import Any

from app.models.entities import Interview

_BASELINE_KEY = "exercise_baseline_code"


def get_exercise_baseline(interview: Interview) -> str:
    settings: dict[str, Any] = interview.ai_settings or {}
    return str(settings.get(_BASELINE_KEY) or "").strip()


def clear_exercise_baseline(interview: Interview) -> None:
    settings = dict(interview.ai_settings or {})
    settings.pop(_BASELINE_KEY, None)
    interview.ai_settings = settings


def set_exercise_baseline(interview: Interview, code: str) -> None:
    text = (code or "").strip()
    if len(text) < 15:
        return
    settings = dict(interview.ai_settings or {})
    settings[_BASELINE_KEY] = text
    interview.ai_settings = settings


def build_code_change_notice(baseline: str, current: str) -> str:
    base = baseline.strip()
    cur = current.strip()
    if not base:
        return ""
    if base == cur:
        return (
            "Код в редакторе совпадает с исходным заданием AI — кандидат пока не внёс правок."
        )
    ratio = difflib.SequenceMatcher(None, base, cur).ratio()
    return (
        f"Код ИЗМЕНЁН кандидатом (схожесть с исходным заданием: {ratio:.0%}). "
        "Оцените конкретные правки. ЗАПРЕЩЕНО утверждать, что код не менялся."
    )
