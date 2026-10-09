"""Когда очищать редактор перед новым ходом AI."""
from __future__ import annotations

import re
from typing import Any

from app.services.competency_utils import skill_to_editor_language
from app.services.transcript_format import question_needs_editor_code

_NEW_EXERCISE_MARKERS = re.compile(
    r"новая\s+задача|новый\s+(?:вопрос|сниппет)|переходим\s+к|"
    r"давайте\s+(?:новую|к\s+новой|следующ)|"
    r"напишите\s+(?:функци|запрос|класс|метод|код)|"
    r"посмотрите[,\s]+пожалуйста,?\s+код|"
    r"разберём\s+код\s+в\s+редакторе|"
    r"код\s+(?:функции|запроса|класса)\s+[«\"`']|"
    r"в\s+редакторе\s+(?:уже\s+)?(?:заготовк|лежит|код)|"
    r"следующ(?:ая|ий)\s+задач|"
    r"перейдём\s+к\s+новой",
    re.I,
)

_CONTINUE_MARKERS = re.compile(
    r"я\s+вижу\s+ваш|ваш[аеи]?\s+(?:реализац|код|запрос|правк|решени)|"
    r"уточню|считаете\s+ли\s+вы|"
    r"как\s+бы\s+вы\s+исправили|"
    r"вернёмся\s+к\s+вашему|"
    r"ваши\s+правки|"
    r"в\s+вашем\s+(?:коде|запросе|решении)|"
    r"переписат[ьи]|перепишите\s+(?:этот|тот)\s+же|"
    r"тот\s+же\s+(?:запрос|код|скрипт)|"
    r"используя\s+оконн|"
    r"на\s+основе\s+(?:вашего|текущего)|"
    r"DENSE_RANK|ROW_NUMBER|LAG\(|LEAD\(",
    re.I,
)


def _has_replace_snippet(code_actions: list[dict[str, Any]] | None) -> bool:
    for action in code_actions or []:
        if not isinstance(action, dict):
            continue
        if action.get("action") != "replace":
            continue
        if str(action.get("text") or "").strip():
            return True
    return False


def should_reset_editor_for_ai_turn(
    *,
    message: str,
    code_actions: list[dict[str, Any]] | None,
    competency_focus: str | None,
    current_editor_language: str,
    format_name: str = "",
    continue_exercise: bool | None = None,
    keep_editor: bool | None = None,
) -> bool:
    """True — очистить редактор до применения code_actions.

    Новый вопрос / новая задача / смена языка → очистить, затем подставить сниппет.
    Продолжение того же упражнения (уточнение по коду кандидата) → оставить.
    """
    if continue_exercise is True or keep_editor is True:
        focus = (competency_focus or "").strip()
        if focus:
            lang = skill_to_editor_language(focus)
            if lang != (current_editor_language or "").strip().lower():
                return True
        return False

    if continue_exercise is False or keep_editor is False:
        return True

    if _has_replace_snippet(code_actions):
        return True

    focus = (competency_focus or "").strip()
    if focus:
        lang = skill_to_editor_language(focus)
        if lang != (current_editor_language or "").strip().lower():
            return True

    text = (message or "").strip()
    if not text:
        return True

    has_continue = bool(_CONTINUE_MARKERS.search(text))
    has_new = bool(_NEW_EXERCISE_MARKERS.search(text))

    if has_new and not has_continue:
        return True
    if has_continue and not has_new:
        return False
    if has_new and has_continue:
        # «правки хороши, теперь новая задача» / «вернёмся к SQL» после Python
        return True

    if question_needs_editor_code(text, format_name=format_name):
        # Нужен код в редакторе, но сниппета нет — убрать чужой/устаревший код
        return True

    # Устный follow-up без кода — редактор не трогаем
    return False


def turn_continue_flags(turn: dict[str, Any]) -> tuple[bool | None, bool | None]:
    cont = turn.get("continue_exercise")
    keep = turn.get("keep_editor")
    cont_b = cont if isinstance(cont, bool) else None
    keep_b = keep if isinstance(keep, bool) else None
    return cont_b, keep_b
