"""Правила применения code_actions от AI (не затирать правки кандидата)."""
from typing import Any

from app.models.entities import Interview
from app.services.code_exercise import get_exercise_baseline


def should_skip_ai_code_action(
    action: dict[str, Any],
    interview: Interview,
    code_before_submit: str,
    answer_type: str,
) -> bool:
    _ = code_before_submit, answer_type
    op = action.get("action", "insert")
    if op != "replace":
        return False

    new_text = (action.get("text") or "").strip()
    current = (interview.editor_content or "").strip()
    if not new_text or new_text == current:
        return True

    baseline = get_exercise_baseline(interview).strip()
    # Не откатывать исходный сниппет поверх правок кандидата; новый сниппет — применяем.
    if baseline and new_text == baseline and current != baseline:
        return True

    return False
