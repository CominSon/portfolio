import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Report
from app.services.report_postprocess import sanitize_report_data
from app.services.scoring_engine import ScoringEngine
from app.services.llm_orchestrator import InterviewContext


class ReportBuilder:
    def __init__(self, scoring_engine: ScoringEngine | None = None) -> None:
        self.scoring_engine = scoring_engine or ScoringEngine()

    async def build_and_persist(
        self, db: AsyncSession, interview_id: uuid.UUID, ctx: InterviewContext
    ) -> Report:
        data = sanitize_report_data(await self.scoring_engine.score_interview(ctx))
        from sqlalchemy import select

        from app.models.entities import Report as ReportModel

        existing = (
            await db.execute(
                select(ReportModel).where(ReportModel.interview_id == interview_id)
            )
        ).scalar_one_or_none()
        if existing:
            existing.competency_scores = data.get("competency_scores", {})
            existing.strengths = data.get("strengths", [])
            existing.weaknesses = data.get("weaknesses", [])
            existing.communication_assessment = data.get("communication_assessment", {})
            existing.code_quality_assessment = data.get("code_quality_assessment", {})
            existing.honesty_signals = data.get("honesty_signals", {})
            existing.confidence_level = float(data.get("confidence_level", 0.5))
            existing.recommendation = data.get("recommendation", "weak_fit")
            existing.final_summary = data.get("final_summary", "")
            return existing
        report = Report(
            interview_id=interview_id,
            competency_scores=data.get("competency_scores", {}),
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            communication_assessment=data.get("communication_assessment", {}),
            code_quality_assessment=data.get("code_quality_assessment", {}),
            honesty_signals=data.get("honesty_signals", {}),
            confidence_level=float(data.get("confidence_level", 0.5)),
            recommendation=data.get("recommendation", "weak_fit"),
            final_summary=data.get("final_summary", ""),
        )
        db.add(report)
        return report
