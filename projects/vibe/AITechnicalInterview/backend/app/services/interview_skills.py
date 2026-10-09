"""Фильтрация навыков и контекста резюме под выбранные компетенции."""
from __future__ import annotations

import re
from typing import Any


def competency_skill_names(competencies: list[dict[str, Any]]) -> list[str]:
    return [str(c.get("skill", "")).strip() for c in competencies if str(c.get("skill", "")).strip()]


def skills_overlap(skill: str, allowed: list[str]) -> bool:
    s = skill.strip().lower()
    if not s:
        return False
    for raw in allowed:
        a = raw.strip().lower()
        if not a:
            continue
        if a in s or s in a:
            return True
        if a == "sql" and re.search(r"\bsql\b|postgres|greenplum|hive|spark", s):
            return True
        if a == "python" and "python" in s:
            return True
    return False


def filter_resume_profile_for_competencies(
    profile: dict[str, Any] | None,
    competencies: list[dict[str, Any]],
) -> dict[str, Any]:
    if not profile:
        return {}
    allowed = competency_skill_names(competencies)
    if not allowed:
        return dict(profile)

    out = dict(profile)
    all_resume_skills = [str(s).strip() for s in (profile.get("key_skills") or []) if str(s).strip()]
    if all_resume_skills:
        filtered = [s for s in all_resume_skills if skills_overlap(s, allowed)]
        out["key_skills"] = filtered or all_resume_skills[:2]

    opening = str(profile.get("opening_question") or "").strip()
    if opening and not opening_matches_competencies(
        opening, allowed, resume_skills=all_resume_skills
    ):
        out.pop("opening_question", None)
    return out


def _skill_mentioned_in_text(skill: str, text: str) -> bool:
    s = skill.lower().strip()
    if not s or not text:
        return False
    if s in text:
        return True
    for token in re.findall(r"[a-zа-яё0-9+#]{3,}", s):
        if len(token) >= 4 and token in text:
            return True
    return False


def opening_matches_competencies(
    opening: str,
    allowed: list[str],
    *,
    resume_skills: list[str] | None = None,
) -> bool:
    """Первый вопрос должен относиться к выбранным компетенциям, не к «лишним» навыкам резюме."""
    text = opening.lower()
    allowed_lower = [a.lower() for a in allowed if a.strip()]
    if not allowed_lower:
        return True

    for skill in resume_skills or []:
        if skills_overlap(str(skill), allowed):
            continue
        if _skill_mentioned_in_text(str(skill), text):
            return False

    if len(allowed_lower) > 1:
        if not any(_skill_mentioned_in_text(skill, text) for skill in allowed_lower):
            return False
    return True


def skills_only_prompt_rule(competencies: list[dict[str, Any]]) -> str:
    names = competency_skill_names(competencies)
    if not names:
        return ""
    joined = ", ".join(names)
    return (
        f"- СТРОГО: задавайте вопросы ТОЛЬКО по компетенциям интервью: {joined}. "
        f"НЕ спрашивайте про другие навыки из резюме или вакансии, если их нет в этом списке.\n"
    )
