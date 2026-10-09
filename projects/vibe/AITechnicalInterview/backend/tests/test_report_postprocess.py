from app.services.report_postprocess import (
    agent_issues_from_transcript,
    sanitize_report_data,
)


def test_agent_issues_detects_generic_replies():
    history = [
        {"speaker": "ai", "text": "Спасибо. Перейдём к следующему аспекту."},
        {"speaker": "candidate", "text": "Какой аспект?"},
    ]
    block = agent_issues_from_transcript(history)
    assert "шаблоном" in block
    assert "STT" in block


def test_sanitize_drops_stt_and_clarification_weaknesses():
    data = {
        "weaknesses": [
            "Допускает опечатки (Love Join вместо LEFT JOIN)",
            "Иногда невнимателен к формулировкам, переспрашивает",
            "Слабее с оконными функциями",
        ],
        "communication_assessment": {
            "итог": "Требовалось уточнение вопроса интервьюера.",
        },
        "final_summary": "Хороший SQL. Иногда переспрашивает.",
    }
    out = sanitize_report_data(data)
    assert len(out["weaknesses"]) == 1
    assert "оконными" in out["weaknesses"][0]
    assert "уточнение" not in out["communication_assessment"]["итог"].lower()
