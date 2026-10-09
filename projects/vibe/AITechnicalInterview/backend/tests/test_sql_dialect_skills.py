from app.services.interview_skills import opening_matches_competencies, skills_overlap
from app.services.sql_dialect import infer_sql_dialect_from_text, resolve_sql_dialect


def test_infer_greenplum_from_jd():
    jd = "Опыт работы с Greenplum, SQL, ETL pipelines"
    assert infer_sql_dialect_from_text(jd) == "Greenplum"


def test_infer_hive_from_jd():
    assert infer_sql_dialect_from_text("Apache Hive, Spark, Hadoop") == "Apache Hive"


def test_resolve_dialect_from_resume_when_jd_generic_sql():
    jd = "Требуется опыт SQL и Python"
    resume = "Стек: PostgreSQL, FastAPI, Kafka"
    assert resolve_sql_dialect(jd, resume) == "PostgreSQL"


def test_resolve_dialect_from_resume_key_skills_when_pdf_text_sparse():
    jd = "SQL обязателен"
    assert resolve_sql_dialect("", "", extra_text="Python, PostgreSQL, Kafka") == "PostgreSQL"


def test_resolve_prefers_specific_jd_over_resume():
    jd = "Greenplum, SQL"
    resume = "PostgreSQL, Python"
    assert resolve_sql_dialect(jd, resume) == "Greenplum"


def test_merge_prefers_regex_over_llm_ansi():
    from app.services.sql_dialect import _merge_llm_and_regex_dialect

    dialect, source = _merge_llm_and_regex_dialect("ANSI SQL", "PostgreSQL")
    assert dialect == "PostgreSQL"
    assert source == "regex"


def test_opening_rejects_off_topic_resume_skill():
    opening = "Расскажите про ваш опыт с Kubernetes в продакшене"
    allowed = ["SQL"]
    resume = ["Kubernetes", "SQL", "Python"]
    assert not opening_matches_competencies(opening, allowed, resume_skills=resume)


def test_opening_accepts_matching_skill():
    opening = "Расскажите про оптимизацию SQL-запросов в Greenplum"
    allowed = ["SQL"]
    resume = ["LLM", "SQL"]
    assert opening_matches_competencies(opening, allowed, resume_skills=resume)


def test_skills_overlap_sql_variants():
    assert skills_overlap("PostgreSQL", ["SQL"])
    assert skills_overlap("Greenplum", ["SQL"])
