"""Тесты политики очистки редактора между ходами AI."""
from app.services.editor_turn_policy import should_reset_editor_for_ai_turn


def test_new_python_review_without_snippet_clears_sql_editor():
    assert should_reset_editor_for_ai_turn(
        message="Разберём код в редакторе по Python: найдите ошибки, риски с NULL и производительность.",
        code_actions=[],
        competency_focus="Python",
        current_editor_language="sql",
        format_name="Live Coding + Code Review",
    )


def test_replace_snippet_resets_then_applies():
    assert should_reset_editor_for_ai_turn(
        message="Посмотрите код функции process_transactions в редакторе.",
        code_actions=[{"action": "replace", "text": "def process_transactions():\n    pass\n"}],
        competency_focus="Python",
        current_editor_language="sql",
        format_name="Live Coding",
    )


def test_follow_up_keeps_candidate_code():
    assert not should_reset_editor_for_ai_turn(
        message="Отлично, я вижу вашу реализацию. Уточню один момент: для пустой строки функция вернёт True. Считаете ли вы это правильным?",
        code_actions=[],
        competency_focus="Python",
        current_editor_language="python",
        format_name="Live Coding",
    )


def test_continue_exercise_flag_keeps_editor():
    assert not should_reset_editor_for_ai_turn(
        message="Как бы вы исправили эту строку?",
        code_actions=[],
        competency_focus="Python",
        current_editor_language="python",
        continue_exercise=True,
    )


def test_continue_flag_but_language_switch_resets():
    assert should_reset_editor_for_ai_turn(
        message="Вернёмся к вашему запросу.",
        code_actions=[],
        competency_focus="SQL",
        current_editor_language="python",
        continue_exercise=True,
    )


def test_language_switch_without_snippet_resets():
    assert should_reset_editor_for_ai_turn(
        message="Хорошо, принято. Переходим к SQL.",
        code_actions=[],
        competency_focus="SQL",
        current_editor_language="python",
        format_name="Live Coding",
    )
