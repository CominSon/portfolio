from app.services.llm_orchestrator import InterviewContext, LlmOrchestrator
from app.services.warmup_quiz import WARMUP_QUIZ_WEIGHT
from app.services.competency_plan import untested_skills


class ScoringEngine:
    def __init__(self, orchestrator: LlmOrchestrator | None = None) -> None:
        self.orchestrator = orchestrator or LlmOrchestrator()

    async def score_interview(self, ctx: InterviewContext) -> dict:
        report = await self.orchestrator.generate_report(ctx)
        scores = dict(report.get("competency_scores") or {})
        missing = untested_skills(
            [
                {
                    "skill": c.get("skill"),
                    "coverage": ctx.coverage.get(c.get("skill", ""), c.get("coverage", 0)),
                }
                for c in (ctx.competencies or [])
            ]
        )
        # Навыки почти без покрытия — не раздувать оценку и явно пометить
        for skill in missing:
            prev = scores.get(skill)
            if prev is None or float(prev) > 40:
                scores[skill] = 35
        if missing:
            weaknesses = list(report.get("weaknesses") or [])
            note = (
                "Не успели полноценно проверить: "
                + ", ".join(missing)
                + " — оценка по этим навыкам ограничена."
            )
            if note not in weaknesses:
                weaknesses.insert(0, note)
            report["weaknesses"] = weaknesses
            report["untested_skills"] = missing
            summary = str(report.get("final_summary") or "")
            if missing and "не успели" not in summary.lower() and "не проверял" not in summary.lower():
                report["final_summary"] = (
                    summary.rstrip()
                    + f" Важно: навыки {', '.join(missing)} в сессии почти не покрыты."
                )
            # Не завышать рекомендацию при дырах в покрытии
            rec = str(report.get("recommendation") or "")
            heavy_missing = [
                c.get("skill")
                for c in (ctx.competencies or [])
                if c.get("skill") in missing and int(c.get("weight") or 0) >= 25
            ]
            if heavy_missing and rec in ("strong_fit", "good_fit"):
                report["recommendation"] = "weak_fit"
        report["competency_scores"] = scores

        if ctx.competencies:
            total_weight = sum(c.get("weight", 1) for c in ctx.competencies) or 1
            weighted = 0.0
            for comp in ctx.competencies:
                skill = comp.get("skill", "")
                w = comp.get("weight", 1)
                if skill in missing:
                    weighted += float(scores.get(skill, 35)) * w
                else:
                    weighted += float(scores.get(skill, ctx.coverage.get(skill, 50))) * w
            interview_score = weighted / total_weight
            quiz_accuracy = None
            mode = ctx.mode_settings or {}
            answers = [
                a
                for a in (mode.get("warmup_quiz_answers") or [])
                if not a.get("excluded_from_score")
            ]
            if answers:
                correct = sum(1 for a in answers if a.get("is_correct"))
                quiz_accuracy = 100.0 * correct / len(answers)
                report["warmup_quiz_offered"] = len(answers)
                report["warmup_quiz_correct"] = correct
            if quiz_accuracy is not None:
                blended = (1.0 - WARMUP_QUIZ_WEIGHT) * interview_score + WARMUP_QUIZ_WEIGHT * quiz_accuracy
                report["aggregate_score"] = round(blended, 2)
                report["warmup_quiz_accuracy"] = round(quiz_accuracy, 1)
                report["warmup_quiz_weight"] = WARMUP_QUIZ_WEIGHT
            else:
                report["aggregate_score"] = round(interview_score, 2)
        return report
