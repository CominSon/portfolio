from app.services.editor_snippets import fallback_editor_snippet


def test_python_orders_snippet_for_user_totals_prompt():
    snippet = fallback_editor_snippet(
        None,  # type: ignore[arg-type]
        competency_focus="Python",
        ai_text="Посмотри на код в редакторе. Функция get_user_totals для списка user_id.",
    )
    assert "get_user_totals" in snippet
    assert "user_id" in snippet
