#!/usr/bin/env python3
"""Экспорт отчёта и стенограммы интервью в exports/."""
import asyncio
import json
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.entities import Candidate, Interview, Transcript
from app.services.datetime_utils import format_moscow
from app.services.report_format import RECOMMENDATION_RU, format_report_text_ru
from app.services.resume_analyzer import candidate_display_name


async def export_interview(interview_id: UUID) -> Path:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Interview)
            .where(Interview.id == interview_id)
            .options(
                selectinload(Interview.competencies),
                selectinload(Interview.report),
                selectinload(Interview.candidate),
            )
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise SystemExit(f"Интервью {interview_id} не найдено")

        tr = await db.execute(
            select(Transcript)
            .where(Transcript.interview_id == interview_id)
            .order_by(Transcript.created_at)
        )
        transcripts = list(tr.scalars().all())

        lines: list[str] = [
            "ЭКСПОРТ ИНТЕРВЬЮ",
            "=" * 60,
            f"interview_id: {interview.id}",
            f"status: {interview.status}",
            f"format: {interview.selected_format}",
            f"editor_language: {interview.editor_language}",
            f"started_at: {interview.started_at}",
            f"ended_at: {interview.ended_at}",
        ]
        if interview.candidate:
            lines.append(f"candidate_email: {interview.candidate.email}")
        lines.append(f"feedback_emails: {json.dumps(interview.feedback_emails or [], ensure_ascii=False)}")
        lines.append("")

        if interview.report:
            r = interview.report
            data = {
                "competency_scores": r.competency_scores or {},
                "strengths": r.strengths or [],
                "weaknesses": r.weaknesses or [],
                "communication_assessment": r.communication_assessment or {},
                "code_quality_assessment": r.code_quality_assessment or {},
                "honesty_signals": r.honesty_signals or {},
                "confidence_level": r.confidence_level,
                "recommendation": r.recommendation,
                "final_summary": r.final_summary or "",
            }
            meta = {
                "candidate_name": candidate_display_name(interview),
                "format": interview.selected_format,
                "editor_language": interview.editor_language,
                "started_at": format_moscow(interview.started_at),
                "ended_at": format_moscow(interview.ended_at),
            }
            lines.append(format_report_text_ru(data, meta))
        else:
            lines.append("ОТЧЁТ: не сформирован")

        lines.extend(["", "СТЕНОГРАММА", "=" * 60, ""])
        for t in transcripts:
            lines.append(f"[{t.speaker}]")
            lines.append(t.text or "")
            lines.append("")

        base = ROOT / "exports"
        base.mkdir(parents=True, exist_ok=True)
        iid_hex = interview.id.hex
        full_path = base / f"interview_{iid_hex}_full.txt"
        full_path.write_text("\n".join(lines), encoding="utf-8")

        if interview.report:
            report_only = format_report_text_ru(
                {
                    "competency_scores": interview.report.competency_scores or {},
                    "strengths": interview.report.strengths or [],
                    "weaknesses": interview.report.weaknesses or [],
                    "communication_assessment": interview.report.communication_assessment or {},
                    "code_quality_assessment": interview.report.code_quality_assessment or {},
                    "honesty_signals": interview.report.honesty_signals or {},
                    "confidence_level": interview.report.confidence_level,
                    "recommendation": interview.report.recommendation,
                    "final_summary": interview.report.final_summary or "",
                },
                {
                    "candidate_name": candidate_display_name(interview),
                    "format": interview.selected_format,
                    "editor_language": interview.editor_language,
                    "started_at": format_moscow(interview.started_at),
                    "ended_at": format_moscow(interview.ended_at),
                },
            )
            report_path = base / f"report_{iid_hex}.txt"
            report_path.write_text(report_only, encoding="utf-8")

        return full_path


async def export_latest() -> Path:
    async with async_session_factory() as db:
        result = await db.execute(
            select(Interview)
            .where(Interview.status.in_(("report_ready", "completed", "completing")))
            .order_by(Interview.ended_at.desc())
            .limit(1)
        )
        interview = result.scalar_one_or_none()
        if not interview:
            raise SystemExit("Завершённых интервью не найдено")
        return await export_interview(interview.id)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raw = sys.argv[1].replace("-", "")
        uid = UUID(raw) if len(raw) == 32 else UUID(sys.argv[1])
        path = asyncio.run(export_interview(uid))
    else:
        path = asyncio.run(export_latest())
    print(f"Сохранено: {path}")
