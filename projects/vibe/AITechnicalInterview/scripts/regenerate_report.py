#!/usr/bin/env python3
"""Перегенерация отчёта на русском для завершённого интервью."""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.entities import Interview
from app.services.datetime_utils import format_moscow
from app.services.interview_session_manager import InterviewSessionManager
from app.services.report_format import format_report_text_ru
from app.services.resume_analyzer import candidate_display_name


async def main(interview_id: str) -> None:
    uid = UUID(interview_id.replace("-", "")) if len(interview_id) == 32 else UUID(interview_id)
    manager = InterviewSessionManager()
    async with async_session_factory() as db:
        result = await db.execute(
            select(Interview)
            .where(Interview.id == uid)
            .options(
                selectinload(Interview.competencies),
                selectinload(Interview.report),
                selectinload(Interview.candidate),
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            print(f"Интервью {interview_id} не найдено")
            sys.exit(1)
        ctx = await manager._build_context(db, interview)
        await manager.report_builder.build_and_persist(db, interview.id, ctx)
        await db.commit()
        await db.refresh(interview, attribute_names=["report"])
        report = interview.report
        if not report:
            print("Отчёт не создан")
            sys.exit(1)
        data = {
            "competency_scores": report.competency_scores or {},
            "strengths": report.strengths or [],
            "weaknesses": report.weaknesses or [],
            "communication_assessment": report.communication_assessment or {},
            "code_quality_assessment": report.code_quality_assessment or {},
            "honesty_signals": report.honesty_signals or {},
            "confidence_level": report.confidence_level,
            "recommendation": report.recommendation,
            "final_summary": report.final_summary or "",
        }
        text = format_report_text_ru(
            data,
            {
                "candidate_name": candidate_display_name(interview),
                "format": interview.selected_format,
                "editor_language": interview.editor_language,
                "started_at": format_moscow(interview.started_at),
                "ended_at": format_moscow(interview.ended_at),
            },
        )
        out = ROOT / "exports" / f"report_{interview.id.hex}.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(text)
        print(f"\nСохранено: {out}")


if __name__ == "__main__":
    iid = sys.argv[1] if len(sys.argv) > 1 else "5eb54bcbe94f41d8a98391b5d0a80571"
    asyncio.run(main(iid))
