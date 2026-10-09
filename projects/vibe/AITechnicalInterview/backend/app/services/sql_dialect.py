"""Определение SQL-диалекта из текста вакансии и резюме (без глобального .env)."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import inspect

from app.models.entities import Interview
from app.services.resume_analyzer import get_resume_profile

SQL_DIALECT_KEY = "sql_dialect"
SQL_DIALECT_SOURCE_KEY = "sql_dialect_source"

ALLOWED_SQL_DIALECTS: tuple[str, ...] = (
    "Greenplum",
    "Apache Hive",
    "Spark SQL",
    "ClickHouse",
    "BigQuery",
    "Oracle",
    "Microsoft SQL Server",
    "MySQL",
    "PostgreSQL",
    "ANSI SQL",
)

# Порядок важен: специфичные диалекты раньше PostgreSQL.
_DIALECT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Greenplum", re.compile(r"greenplum|gpdb", re.I)),
    ("Apache Hive", re.compile(r"\bhive\b|hiveql", re.I)),
    ("Spark SQL", re.compile(r"spark\s*sql|pyspark", re.I)),
    ("ClickHouse", re.compile(r"clickhouse", re.I)),
    ("BigQuery", re.compile(r"big\s*query|bigquery", re.I)),
    ("Oracle", re.compile(r"\boracle\b|pl\s*/\s*sql", re.I)),
    ("Microsoft SQL Server", re.compile(r"sql\s*server|mssql|\bt-?sql\b", re.I)),
    ("MySQL", re.compile(r"\bmysql\b|mariadb", re.I)),
    ("PostgreSQL", re.compile(r"postgresql|postgres|\bpg\b|постгре", re.I)),
)

_SQL_CONTEXT = re.compile(
    r"\bsql\b|greenplum|hive|spark\s*sql|clickhouse|bigquery|oracle|postgres|mysql|sql\s*server",
    re.I,
)


def _competencies_loaded(interview: Interview) -> bool:
    return "competencies" not in inspect(interview).unloaded


def interview_has_sql_competency(interview: Interview) -> bool:
    if not _competencies_loaded(interview):
        return False
    for c in interview.competencies or []:
        if "sql" in (c.skill or "").lower():
            return True
    return False


def infer_sql_dialect_from_text(text: str) -> str | None:
    """Эвристика по тексту вакансии, резюме или JD."""
    blob = (text or "").strip()
    if not blob or not _SQL_CONTEXT.search(blob):
        return None
    for name, pattern in _DIALECT_PATTERNS:
        if pattern.search(blob):
            return name
    return "ANSI SQL"


def _is_specific_dialect(dialect: str | None) -> bool:
    return bool(dialect and dialect != "ANSI SQL")


def resolve_sql_dialect(job_text: str, resume_text: str, *, extra_text: str = "") -> str | None:
    """
    Приоритет: явный диалект в вакансии → конкретный диалект в резюме → ANSI SQL.
    Если в вакансии только «SQL» без диалекта — смотрим резюме кандидата.
    """
    jd = (job_text or "").strip()
    resume_blob = "\n".join(
        part.strip() for part in (resume_text or "", extra_text or "") if part and part.strip()
    )
    jd_dialect = infer_sql_dialect_from_text(jd) if jd else None
    resume_dialect = infer_sql_dialect_from_text(resume_blob) if resume_blob else None

    if _is_specific_dialect(jd_dialect):
        return jd_dialect
    if _is_specific_dialect(resume_dialect):
        return resume_dialect
    if jd_dialect:
        return jd_dialect
    return resume_dialect


def _resume_supplemental_text(interview: Interview) -> str:
    """Навыки из LLM-профиля резюме и подтверждённых компетенций (fallback, если PDF плохо распарсился)."""
    chunks: list[str] = []
    profile = get_resume_profile(interview) or {}
    for skill in profile.get("key_skills") or []:
        s = str(skill).strip()
        if s:
            chunks.append(s)
    if _competencies_loaded(interview):
        for c in interview.competencies or []:
            s = str(c.skill or "").strip()
            if s:
                chunks.append(s)
    return ", ".join(chunks)


def resolve_interview_sql_dialect(interview: Interview) -> str | None:
    jd = (interview.job_description_text or "").strip()
    resume = (interview.resume_text or "").strip()
    extra = _resume_supplemental_text(interview)
    return resolve_sql_dialect(jd, resume, extra_text=extra)


def get_stored_sql_dialect(interview: Interview) -> str | None:
    settings: dict[str, Any] = interview.ai_settings or {}
    raw = str(settings.get(SQL_DIALECT_KEY) or "").strip()
    return raw or None


def normalize_sql_dialect_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = str(raw).strip()
    if not name:
        return None
    low = name.lower()
    if low in ("none", "null", "нет", "не указан", "неизвестно"):
        return None
    for allowed in ALLOWED_SQL_DIALECTS:
        if allowed.lower() == low:
            return allowed
    aliases = {
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "pg": "PostgreSQL",
        "mssql": "Microsoft SQL Server",
        "sql server": "Microsoft SQL Server",
        "t-sql": "Microsoft SQL Server",
        "tsql": "Microsoft SQL Server",
        "hive": "Apache Hive",
        "hiveql": "Apache Hive",
        "spark": "Spark SQL",
        "ansi": "ANSI SQL",
        "standard sql": "ANSI SQL",
    }
    return aliases.get(low)


def set_interview_sql_dialect(interview: Interview, dialect: str | None, *, source: str | None = None) -> None:
    settings = dict(interview.ai_settings or {})
    if dialect:
        settings[SQL_DIALECT_KEY] = dialect.strip()
        if source:
            settings[SQL_DIALECT_SOURCE_KEY] = source
    else:
        settings.pop(SQL_DIALECT_KEY, None)
        settings.pop(SQL_DIALECT_SOURCE_KEY, None)
    interview.ai_settings = settings


def _should_infer_sql_dialect(interview: Interview) -> bool:
    if _competencies_loaded(interview) and interview_has_sql_competency(interview):
        return True
    jd = (interview.job_description_text or "").strip()
    resume = (interview.resume_text or "").strip()
    extra = _resume_supplemental_text(interview)
    blob = "\n".join(part for part in (jd, resume, extra) if part)
    return bool(blob and _SQL_CONTEXT.search(blob))


def _merge_llm_and_regex_dialect(
    llm_dialect: str | None,
    regex_dialect: str | None,
) -> tuple[str | None, str]:
    """
    LLM может ошибочно вернуть ANSI SQL при PostgreSQL в резюме.
    Конкретный диалект из regex важнее generic ANSI от модели.
    """
    if _is_specific_dialect(llm_dialect):
        return llm_dialect, "llm"
    if _is_specific_dialect(regex_dialect):
        return regex_dialect, "regex"
    if llm_dialect:
        return llm_dialect, "llm"
    if regex_dialect:
        return regex_dialect, "regex"
    return None, "regex"


async def sync_interview_sql_dialect_async(
    interview: Interview,
    orchestrator: Any | None = None,
) -> str | None:
    """
    Определить диалект через LLM (вакансия + резюме), срезервом regex.
    Конкретный диалект из текста важнее «ANSI SQL» от модели.
    """
    if _competencies_loaded(interview) and not interview_has_sql_competency(interview):
        set_interview_sql_dialect(interview, None)
        return None
    if not _should_infer_sql_dialect(interview):
        return get_stored_sql_dialect(interview)

    regex_dialect = resolve_interview_sql_dialect(interview)
    llm_dialect: str | None = None
    try:
        from app.services.llm_orchestrator import LlmOrchestrator

        orch = orchestrator or LlmOrchestrator()
        jd = (interview.job_description_text or "").strip()
        resume = (interview.resume_text or "").strip()
        extra = _resume_supplemental_text(interview)
        skills = [s.strip() for s in extra.split(",") if s.strip()] if extra else []
        llm_dialect = normalize_sql_dialect_name(
            await orch.infer_sql_dialect(jd, resume, supplemental_skills=skills)
        )
    except Exception:
        llm_dialect = None

    dialect, source = _merge_llm_and_regex_dialect(llm_dialect, regex_dialect)

    if dialect:
        set_interview_sql_dialect(interview, dialect, source=source)
        return dialect
    if _competencies_loaded(interview) and interview_has_sql_competency(interview):
        set_interview_sql_dialect(interview, "ANSI SQL", source="default")
        return "ANSI SQL"
    return get_stored_sql_dialect(interview)


def sync_interview_sql_dialect(interview: Interview) -> str | None:
    """
    Синхронный fallback (только regex). В async-коде используйте sync_interview_sql_dialect_async.
    """
    dialect = resolve_interview_sql_dialect(interview)
    if dialect:
        set_interview_sql_dialect(interview, dialect, source="regex")
        return dialect
    if _competencies_loaded(interview) and not interview_has_sql_competency(interview):
        set_interview_sql_dialect(interview, None)
    return get_stored_sql_dialect(interview)


def get_interview_sql_dialect(interview: Interview) -> str | None:
    if not interview_has_sql_competency(interview):
        return None
    resolved = resolve_interview_sql_dialect(interview)
    if _is_specific_dialect(resolved):
        stored = get_stored_sql_dialect(interview)
        if resolved != stored:
            set_interview_sql_dialect(interview, resolved, source="regex")
        return resolved
    stored = get_stored_sql_dialect(interview)
    if stored:
        return stored
    if resolved:
        set_interview_sql_dialect(interview, resolved, source="regex")
        return resolved
    return "ANSI SQL"


def sql_dialect_prompt_hint(dialect: str | None) -> str:
    if not dialect:
        return ""
    return (
        f"Для SQL-задач используй диалект: **{dialect}** (из вакансии или резюме). "
        f"В начале КАЖДОГО SQL-вопроса устно скажи: «Диалект: {dialect}» "
        f"(или «Считаем диалект {dialect}»). Синтаксис и функции — только этого диалекта."
    )
