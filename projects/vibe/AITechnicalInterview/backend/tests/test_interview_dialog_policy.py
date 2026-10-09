from app.services.interview_dialog_policy import (
    apply_dialog_policy_to_turn,
    candidate_answer_is_substantive,
    candidate_wants_to_move_on,
    is_vague_explain_request,
)


def test_substantive_long_answer():
    text = " ".join(["слово"] * 50)
    assert candidate_answer_is_substantive(text)


def test_vague_explain_detected():
    assert is_vague_explain_request("Спасибо. Можете подробнее объяснить ваше решение?")


def test_apply_policy_replaces_vague_after_substantive():
    answer = "Я использовал оконную функцию потому что она эффективнее подзапроса на больших таблицах. " * 3
    turn = apply_dialog_policy_to_turn(
        {"message": "Можете подробнее объяснить ваше решение?", "code_actions": []},
        transcript_history=[],
        candidate_answer=answer,
        language="sql",
    )
    assert "подробнее объяснить" not in turn["message"].lower()
    assert len(turn["message"]) > 20


def test_move_on_phrase():
    assert candidate_wants_to_move_on("Да я всё объяснил, давай пропустим и идём дальше.")
