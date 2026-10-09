from app.services.resume_analyzer import ResumeAnalyzer


def test_mock_profile_does_not_dump_pii_in_opening():
    resume = """
    Иван Петров
    Москва, ул. Ленина 5
    мужчина, 1990 г.р.
    ivan@mail.ru +7 999 000-00-00

    Ключевые навыки: RAG, LLM, Python, FastAPI

    Опыт:
    Senior ML Engineer, Сбер, 2023–2025
  """
    profile = ResumeAnalyzer()._mock_profile(resume, ["Python"])
    opening = profile["opening_question"].lower()
    assert "ул." not in opening
    assert "мужчин" not in opening
    assert "mail.ru" not in opening
    assert profile["candidate_first_name"] == "Иван"
    assert profile["candidate_full_name"] == "Иван Петров"
    assert "RAG" in profile["key_skills"] or "LLM" in profile["key_skills"]
    assert "rag" in opening or "llm" in opening or "python" in opening
