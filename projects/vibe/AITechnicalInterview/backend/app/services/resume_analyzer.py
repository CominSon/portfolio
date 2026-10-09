"""Анализ резюме через LLM: профиль кандидата без PII, персональный первый вопрос."""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

RESUME_PROFILE_KEY = "resume_profile"


def get_resume_profile(interview) -> dict[str, Any] | None:
    settings = interview.ai_settings if isinstance(interview.ai_settings, dict) else {}
    profile = settings.get(RESUME_PROFILE_KEY)
    return profile if isinstance(profile, dict) and profile else None


def candidate_display_name(interview) -> str:
    """ФИО для отчётов: Candidate.name или из профиля резюме.

    Не делает lazy-load relationship (безопасно в async без greenlet).
    """
    cand = None
    try:
        from sqlalchemy import inspect as sa_inspect

        state = sa_inspect(interview)
        if "candidate" not in state.unloaded:
            cand = interview.candidate
    except Exception:
        cand = getattr(interview, "__dict__", {}).get("candidate")
    if cand is not None:
        name = (getattr(cand, "name", None) or "").strip()
        if name:
            return name
    profile = get_resume_profile(interview) or {}
    return (
        str(profile.get("candidate_full_name") or "").strip()
        or str(profile.get("candidate_first_name") or "").strip()
    )


def set_resume_profile(interview, profile: dict[str, Any]) -> None:
    settings = dict(interview.ai_settings or {})
    settings[RESUME_PROFILE_KEY] = profile
    interview.ai_settings = settings


def profile_summary_for_prompt(
    profile: dict[str, Any] | None,
    *,
    allowed_skills: list[str] | None = None,
) -> str:
    if not profile:
        return ""
    parts = []
    if profile.get("candidate_first_name"):
        parts.append(f"Имя: {profile['candidate_first_name']}")
    if profile.get("seniority"):
        parts.append(f"Уровень: {profile['seniority']}")
    if profile.get("key_skills"):
        from app.services.interview_skills import skills_overlap

        skills = list(profile["key_skills"][:8])
        if allowed_skills:
            filtered = [s for s in skills if skills_overlap(str(s), allowed_skills)]
            if filtered:
                skills = filtered
        parts.append(f"Ключевые навыки (по выбранным компетенциям): {', '.join(skills)}")
    if profile.get("last_role_title"):
        line = profile["last_role_title"]
        if profile.get("last_company"):
            line += f" @ {profile['last_company']}"
        parts.append(f"Последняя роль: {line}")
    if profile.get("last_role_summary"):
        parts.append(f"Суть роли: {profile['last_role_summary']}")
    if profile.get("achievements"):
        parts.append("Достижения: " + "; ".join(profile["achievements"][:3]))
    return "\n".join(parts)


class ResumeAnalyzer:
    def __init__(self, orchestrator=None) -> None:
        self._orchestrator = orchestrator

    @property
    def orchestrator(self):
        if self._orchestrator is None:
            from app.services.llm_orchestrator import LlmOrchestrator

            self._orchestrator = LlmOrchestrator()
        return self._orchestrator

    async def analyze(
        self,
        resume_text: str,
        *,
        job_description: str | None = None,
        competency_skills: list[str] | None = None,
    ) -> dict[str, Any]:
        resume = (resume_text or "").strip()
        if not resume:
            return {}
        if self.orchestrator.settings.mock_ai or not self.orchestrator.llm.api_key:
            return self._mock_profile(resume, competency_skills or [])

        jd = (job_description or "").strip()[:4000]
        skills_hint = ", ".join(competency_skills or []) or "не заданы"
        prompt = f"""Проанализируй резюме кандидата для подготовки технического AI-интервью.

СТРОГО ЗАПРЕЩЕНО извлекать, сохранять или озвучивать:
- адрес, город, страна, метро, район
- пол, возраст, дата рождения, семейное положение
- телефон, email, мессенджеры, ссылки на соцсети (кроме GitHub/портфолио как факт наличия)
- гражданство, разрешение на работу, водительские права
- фото, рост, вес и прочие личные данные

Извлеки ТОЛЬКО профессиональную информацию:
- полное ФИО кандидата, если явно указано в резюме (например «Иван Петров» или «Иванов Иван Иванович»; если неуверенно — пустая строка)
- имя для вежливого обращения (только имя, например «Иван»; если неуверенно — пустая строка)
- уровень (Junior/Middle/Senior/Lead) по опыту
- ключевые технические навыки (до 8): только из пересечения с компетенциями вакансии ({skills_hint})
- последняя/текущая позиция: должность, компания (можно обезличить до отрасли), 1–2 предложения сути
- до 3 конкретных достижений (метрики, результат, технологии)

Сформируй opening_question — полный текст ПЕРВОЙ реплики интервьюера на русском:
- обратись по имени, если имя известно («Иван, …»)
- НЕ перечисляй резюме и НЕ зачитывай его
- если в компетенциях вакансии есть навыки — первый вопрос по ним (приоритет вакансии)
- только если компетенции вакансии пустые/неинформативные — опирайся на резюме
- задай ОДИН конкретный вопрос (проект, архитектура, ошибки, компромиссы), а не общий
- не задавай общий «расскажите про весь опыт»
- в конце можно напомнить про кнопку «Ответить», но не обязательно

Компетенции вакансии (приоритет №1 для первого вопроса): {skills_hint}
Фрагмент вакансии (если есть):
{jd or "(нет)"}

Резюме:
{resume[:14000]}

Верни ТОЛЬКО JSON:
{{
  "candidate_full_name": "ФИО или пусто",
  "candidate_first_name": "строка или пусто",
  "seniority": "Junior"|"Middle"|"Senior"|"Lead",
  "key_skills": ["..."],
  "last_role_title": "строка",
  "last_company": "строка или пусто",
  "last_role_summary": "1-2 предложения",
  "achievements": ["..."],
  "opening_question": "полный текст первой реплики на русском"
}}"""
        raw = await self.orchestrator._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты HR-аналитик для технических интервью. "
                        "Соблюдай приватность: никаких PII. Отвечай только валидным JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
        )
        profile = self.orchestrator._parse_json(raw, default={})
        return self._normalize_profile(profile, resume, competency_skills or [])

    def _normalize_profile(
        self,
        profile: dict[str, Any],
        resume: str,
        competency_skills: list[str],
    ) -> dict[str, Any]:
        if not isinstance(profile, dict):
            profile = {}
        raw_first = re.sub(r"\s+", " ", str(profile.get("candidate_first_name") or "").strip())
        full_name = re.sub(r"\s+", " ", str(profile.get("candidate_full_name") or "").strip())
        if full_name and len(full_name.split()) > 4:
            full_name = " ".join(full_name.split()[:3])
        if not full_name and 2 <= len(raw_first.split()) <= 4:
            full_name = raw_first
        name = raw_first.split()[0] if raw_first else ""
        if not name and full_name:
            name = full_name.split()[0]
        key_skills = profile.get("key_skills") or []
        if not isinstance(key_skills, list):
            key_skills = []
        key_skills = [str(s).strip() for s in key_skills if str(s).strip()][:8]
        achievements = profile.get("achievements") or []
        if not isinstance(achievements, list):
            achievements = []
        achievements = [str(a).strip() for a in achievements if str(a).strip()][:3]

        opening = str(profile.get("opening_question") or "").strip()
        if not opening or self._looks_like_resume_dump(opening):
            opening = self._fallback_opening(name, key_skills, competency_skills)

        return {
            "candidate_full_name": full_name,
            "candidate_first_name": name,
            "seniority": str(profile.get("seniority") or "").strip() or "Middle",
            "key_skills": key_skills,
            "last_role_title": str(profile.get("last_role_title") or "").strip(),
            "last_company": str(profile.get("last_company") or "").strip(),
            "last_role_summary": str(profile.get("last_role_summary") or "").strip(),
            "achievements": achievements,
            "opening_question": opening,
        }

    @staticmethod
    def _looks_like_resume_dump(text: str) -> bool:
        low = text.lower()
        pii_markers = (
            "ул.",
            "улица",
            "прожива",
            "родил",
            "пол:",
            "мужчин",
            "женщин",
            "год рожд",
            "телефон",
            "email",
            "@",
        )
        if sum(1 for m in pii_markers if m in low) >= 2:
            return True
        if len(text) > 600:
            return True
        return False

    def _fallback_opening(
        self,
        name: str,
        key_skills: list[str],
        competency_skills: list[str],
    ) -> str:
        focus_skill = ""
        # Приоритет: вакансийные компетенции > резюме.
        for pool in (competency_skills, key_skills):
            for s in pool:
                if s:
                    focus_skill = s
                    break
            if focus_skill:
                break
        greet = f"{name}, " if name else ""
        if focus_skill:
            topic = focus_skill
            if topic.upper() in ("RAG", "LLM"):
                q = (
                    f"{greet}давайте начнём с вашего опыта в {topic}: "
                    f"опишите один конкретный проект — задачу, вашу роль и как вы это реализовали."
                )
            else:
                q = (
                    f"{greet}расскажите о последнем проекте, где вы активно использовали {topic}: "
                    f"какая была ваша зона ответственности и какой стек?"
                )
        else:
            q = (
                f"{greet}расскажите о последнем техническом проекте: "
                f"ваша роль, стек и главный результат."
            )
        return q + " Говорите свободно — микрофон записывает всё время. Когда закончите ответ, нажмите «Ответить»."

    def _mock_profile(self, resume: str, competency_skills: list[str]) -> dict[str, Any]:
        key_skills: list[str] = []
        for kw in (
            "RAG",
            "LLM",
            "GPT",
            "LangChain",
            "Python",
            "FastAPI",
            "Kubernetes",
            "PostgreSQL",
            "Java",
            "Go",
            "TypeScript",
            "React",
            "ML",
            "NLP",
        ):
            if re.search(rf"\b{re.escape(kw)}\b", resume, re.IGNORECASE):
                key_skills.append(kw)
        name = ""
        full_name = ""
        first_lines = [ln.strip() for ln in resume.splitlines()[:5] if ln.strip()]
        for line in first_lines:
            if "@" in line or re.search(r"\d{3}", line):
                continue
            words = re.findall(r"[А-ЯЁA-Z][а-яёa-z]+", line)
            if 1 <= len(words) <= 3:
                full_name = " ".join(words)
                name = words[0]
                break
        opening = self._fallback_opening(name, key_skills, competency_skills)
        return {
            "candidate_full_name": full_name,
            "candidate_first_name": name,
            "seniority": "Middle",
            "key_skills": key_skills[:8],
            "last_role_title": "",
            "last_company": "",
            "last_role_summary": "",
            "achievements": [],
            "opening_question": opening,
        }
