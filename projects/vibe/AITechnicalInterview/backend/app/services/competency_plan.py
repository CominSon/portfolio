"""План компетенций: идём по навыкам по очереди с учётом времени."""
from __future__ import annotations

from typing import Any


def _skills_ordered(competencies: list[dict]) -> list[str]:
    """По убыванию веса; при равном весе — порядок из вакансии/админки."""
    items = [(i, c) for i, c in enumerate(competencies) if (c.get("skill") or "").strip()]
    items.sort(key=lambda ic: (-int(ic[1].get("weight") or 0), ic[0]))
    return [str(ic[1]["skill"]) for ic in items]


def ensure_skill_plan(interview, competencies: list[dict]) -> dict[str, Any]:
    """Инициализировать/вернуть план обхода навыков в ai_settings."""
    settings = dict(interview.ai_settings or {})
    ordered = _skills_ordered(competencies)
    plan = list(settings.get("skill_focus_queue") or [])
    if not plan or set(plan) != set(ordered):
        plan = ordered
        settings["skill_focus_queue"] = plan
    if "skill_turn_counts" not in settings or not isinstance(settings["skill_turn_counts"], dict):
        settings["skill_turn_counts"] = {s: 0 for s in plan}
    else:
        for s in plan:
            settings["skill_turn_counts"].setdefault(s, 0)
    if "active_skill" not in settings or settings["active_skill"] not in plan:
        settings["active_skill"] = plan[0] if plan else ""
    interview.ai_settings = settings
    return settings


def preferred_competency(
    interview,
    competencies: list[dict],
    *,
    remaining_minutes: int,
    duration_minutes: int,
) -> str:
    """Какой навык сейчас вести: блок по времени/ходам, потом следующий."""
    settings = ensure_skill_plan(interview, competencies)
    plan: list[str] = list(settings.get("skill_focus_queue") or [])
    if not plan:
        return ""
    counts: dict[str, int] = dict(settings.get("skill_turn_counts") or {})
    duration = max(int(duration_minutes or 60), 1)
    remaining = max(int(remaining_minutes), 0)
    elapsed = max(0, duration - remaining)
    weights = {str(c.get("skill")): max(1, int(c.get("weight") or 1)) for c in competencies}
    total_w = sum(weights.get(s, 1) for s in plan) or 1

    min_turns = 2 if duration >= 40 else 1
    budgets = {s: max(8, int(duration * weights.get(s, 1) / total_w)) for s in plan}

    active = settings.get("active_skill") or plan[0]
    if active not in plan:
        active = plan[0]

    idx = plan.index(active)
    turns_here = int(counts.get(active, 0))

    spent_estimate = sum(budgets[s] for s in plan[:idx])
    current_spent = max(0, elapsed - spent_estimate)

    switch = False
    if turns_here >= min_turns and current_spent >= budgets[active] * 0.85:
        switch = True
    untested_ahead = [s for s in plan[idx + 1 :] if int(counts.get(s, 0)) == 0]
    if untested_ahead and remaining <= max(12, 8 * len(untested_ahead)):
        if turns_here >= 1:
            switch = True
    if remaining <= 8 and untested_ahead:
        switch = True

    if switch and idx + 1 < len(plan):
        active = plan[idx + 1]
        settings["active_skill"] = active
        interview.ai_settings = settings

    return active


def record_skill_coverage(interview, competency_focus: str | None, competencies: list) -> None:
    """Увеличить coverage_score и счётчик ходов по навыку."""
    focus = (competency_focus or "").strip()
    if not focus:
        return
    settings = dict(interview.ai_settings or {})
    counts = dict(settings.get("skill_turn_counts") or {})
    match = None
    for c in competencies:
        skill = str(c.skill if hasattr(c, "skill") else c.get("skill", ""))
        if (
            skill.lower() == focus.lower()
            or focus.lower() in skill.lower()
            or skill.lower() in focus.lower()
        ):
            match = skill
            break
    if not match:
        match = focus
    counts[match] = int(counts.get(match, 0)) + 1
    settings["skill_turn_counts"] = counts
    settings["active_skill"] = match
    interview.ai_settings = settings

    for c in competencies:
        skill = str(c.skill if hasattr(c, "skill") else "")
        if skill.lower() == match.lower():
            prev = float(getattr(c, "coverage_score", 0) or 0)
            c.coverage_score = min(1.0, round(prev + 0.25, 2))
            break


def untested_skills(competencies: list) -> list[str]:
    out = []
    for c in competencies:
        skill = str(c.skill if hasattr(c, "skill") else c.get("skill", ""))
        cov = float(
            c.coverage_score if hasattr(c, "coverage_score") else c.get("coverage", 0) or 0
        )
        if skill and cov < 0.15:
            out.append(skill)
    return out


def difficulty_for_levels(competencies: list[dict]) -> str:
    """Стартовая сложность по заявленным уровням."""
    levels = " ".join(str(c.get("level") or "") for c in competencies).lower()
    if "lead" in levels or "principal" in levels:
        return "hard"
    if "senior" in levels:
        return "hard"
    if "middle" in levels or "mid" in levels:
        return "medium"
    return "easy"


def skill_plan_prompt_block(preferred: str, competencies: list[dict], remaining: int) -> str:
    if not preferred:
        return ""
    ordered = _skills_ordered(competencies)
    return (
        f"\nSKILL PROGRAM (обязательно):\n"
        f"- Сейчас ведите блок по навыку: {preferred}. "
        f"Не прыгайте на другой навык, пока не закроете 1–2 substantive задачи по текущему "
        f"(кроме случая Remaining minutes мало и есть нераскрытые навыки).\n"
        f"- Порядок блоков: {' → '.join(ordered)}.\n"
        f"- competency_focus в JSON должен быть «{preferred}» "
        f"(или следующий по плану при нехватке времени).\n"
        f"- Сложность задач — строго под заявленный level навыка "
        f"(Senior ≠ баг «алиас в WHERE»).\n"
        f"- Не начинайте каждую сессию с is_palindrome / «второй заказ» — варьируйте задачи.\n"
        f"- Remaining minutes: {remaining}.\n"
    )
