"""Счётчик ходов, сложность, список уже заданных вопросов."""
from typing import Any

GENERIC_AI_MESSAGES = frozenset(
    {
        "Спасибо, приняла. Перейдём к следующему аспекту — ответьте кратко или внесите правку в редактор.",
        "Спасибо за ответ. Перейдём к следующему пункту — кратко ответьте или обновите код в редакторе.",
    }
)

_DIFFICULTY_ORDER = ("easy", "medium", "hard")


def is_generic_ai_message(message: str) -> bool:
    t = (message or "").strip()
    if t in GENERIC_AI_MESSAGES:
        return True
    if "перейдём к следующему аспекту" in t.lower() and len(t) < 120:
        return True
    return False


def get_progress(ai_settings: dict | None) -> dict[str, Any]:
    s = dict(ai_settings or {})
    return {
        "ai_turn_count": int(s.get("ai_turn_count", 0)),
        "current_difficulty": s.get("current_difficulty", "easy"),
        "asked_snippets": list(s.get("asked_snippets", [])),
    }


def save_progress(interview, progress: dict[str, Any]) -> None:
    s = dict(interview.ai_settings or {})
    s.update(progress)
    interview.ai_settings = s


def bump_after_answer(interview, candidate_answer: str, *, substantive: bool) -> dict[str, Any]:
    p = get_progress(interview.ai_settings)
    p["ai_turn_count"] = p["ai_turn_count"] + 1
    diff = p.get("current_difficulty", "easy")
    if substantive and diff in _DIFFICULTY_ORDER:
        idx = _DIFFICULTY_ORDER.index(diff)
        if idx < len(_DIFFICULTY_ORDER) - 1:
            p["current_difficulty"] = _DIFFICULTY_ORDER[idx + 1]
    save_progress(interview, p)
    return p


def register_ai_question(interview, message: str) -> None:
    snippet = (message or "").strip()[:200]
    if not snippet or is_generic_ai_message(snippet):
        return
    p = get_progress(interview.ai_settings)
    asked: list[str] = list(p.get("asked_snippets", []))
    if snippet not in asked:
        asked.append(snippet)
    p["asked_snippets"] = asked[-12:]
    save_progress(interview, p)


def asked_questions_block(ai_settings: dict | None) -> str:
    asked = get_progress(ai_settings).get("asked_snippets", [])
    if not asked:
        return ""
    lines = "\n".join(f"- {q[:180]}" for q in asked[-8:])
    return f"\nУже заданные вопросы (НЕ повторять дословно):\n{lines}\n"
