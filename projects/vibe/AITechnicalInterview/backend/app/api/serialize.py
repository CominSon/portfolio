"""Сериализация ORM → Pydantic в async-контексте (без MissingGreenlet)."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Employer, Interview, Report
from app.schemas.common import CompetencyItem, EmployerResponse
from app.schemas.interview import InterviewResponse, ReportResponse, TranscriptItem, WarmupQuizQuestion
from app.config import get_settings
from app.services.tts_prepare import briefing_text as build_briefing_text
from app.services.transcript_manager import TranscriptManager
from app.services.datetime_utils import format_moscow
from app.services.report_format import RECOMMENDATION_RU, format_report_text_ru
from app.services.resume_analyzer import candidate_display_name
from app.services.warmup_quiz import get_warmup_quiz_public, warmup_quiz_stats
from app.services.interview_formats import get_live_coding_ai_assistant, get_session_mode, interview_test_max_turns
from app.services.sql_dialect import get_interview_sql_dialect

_transcripts = TranscriptManager()


async def employer_to_response(db: AsyncSession, employer: Employer) -> EmployerResponse:
    await db.refresh(employer)
    return EmployerResponse(
        id=employer.id,
        name=employer.name,
        email=employer.email,
        contact_emails=list(employer.contact_emails or []),
        created_at=employer.created_at,
    )


async def interview_to_response(
    db: AsyncSession,
    interview: Interview,
    link: str | None = None,
    *,
    include_session: bool = False,
    briefing_text: str | None = None,
    briefing_audio_url: str | None = None,
    warmup_quiz: list | None = None,
) -> InterviewResponse:
    await db.refresh(interview)
    # competencies + candidate: без lazy-load в sync-контексте (MissingGreenlet)
    await db.refresh(interview, attribute_names=["competencies", "candidate"])
    competencies = [
        CompetencyItem(skill=c.skill, level=c.level, weight=c.weight, source=c.source)
        for c in list(interview.competencies)
    ]
    transcripts: list[TranscriptItem] = []
    if include_session:
        history = await _transcripts.get_history(db, interview.id)
        briefing_filter = briefing_text or build_briefing_text(get_settings().effective_tts_voice)
        transcripts = [
            TranscriptItem(speaker=h["speaker"], text=h["text"])
            for h in history
            if not (h.get("speaker") == "ai" and (h.get("text") or "") == briefing_filter)
        ]
    quiz_items = warmup_quiz if warmup_quiz is not None else get_warmup_quiz_public(interview)
    warmup_quiz_models = [
        WarmupQuizQuestion(
            id=str(q.get("id", "")),
            skill=str(q.get("skill", "")),
            question=str(q.get("question", "")),
            options=[str(o) for o in (q.get("options") or [])],
        )
        for q in quiz_items
    ]
    return InterviewResponse(
        id=interview.id,
        status=interview.status,
        access_token=interview.access_token,
        candidate_link=link,
        selected_format=interview.selected_format,
        allowed_formats=interview.allowed_formats or [],
        format_selection_mode=interview.format_selection_mode,
        duration_minutes=interview.duration_minutes,
        editor_language=interview.editor_language,
        editor_content=interview.editor_content,
        media_camera=interview.media_camera,
        media_microphone=interview.media_microphone,
        media_screenshare=interview.media_screenshare,
        competencies=competencies,
        feedback_emails=list(interview.feedback_emails or []),
        started_at=interview.started_at,
        transcripts=transcripts,
        briefing_text=briefing_text,
        briefing_audio_url=briefing_audio_url,
        warmup_quiz=warmup_quiz_models,
        live_coding_ai_assistant=get_live_coding_ai_assistant(interview),
        sql_dialect=get_interview_sql_dialect(interview),
        session_mode=get_session_mode(interview),
        test_max_turns=interview_test_max_turns(interview) if get_session_mode(interview) == "test" else None,
        candidate_name=candidate_display_name(interview) or None,
        created_at=interview.created_at,
    )


async def report_to_response(
    db: AsyncSession,
    report: Report,
    *,
    interview: Interview | None = None,
) -> ReportResponse:
    await db.refresh(report)
    rec = report.recommendation or "weak_fit"
    data = {
        "competency_scores": report.competency_scores or {},
        "strengths": report.strengths or [],
        "weaknesses": report.weaknesses or [],
        "communication_assessment": report.communication_assessment or {},
        "code_quality_assessment": report.code_quality_assessment or {},
        "honesty_signals": report.honesty_signals or {},
        "confidence_level": report.confidence_level,
        "recommendation": rec,
        "final_summary": report.final_summary or "",
    }
    if interview:
        quiz = warmup_quiz_stats(interview)
        if quiz:
            from app.services.warmup_quiz import WARMUP_QUIZ_WEIGHT

            data["warmup_quiz_offered"] = quiz["offered"]
            data["warmup_quiz_correct"] = quiz["correct"]
            data["warmup_quiz_accuracy"] = quiz["accuracy"]
            data["warmup_quiz_weight"] = WARMUP_QUIZ_WEIGHT
    meta: dict = {}
    if interview:
        await db.refresh(interview)
        meta = {
            "candidate_name": candidate_display_name(interview),
            "format": interview.selected_format,
            "editor_language": interview.editor_language,
            "started_at": format_moscow(interview.started_at),
            "ended_at": format_moscow(interview.ended_at),
        }
    return ReportResponse(
        **data,
        recommendation_ru=RECOMMENDATION_RU.get(rec, rec),
        report_text=format_report_text_ru(data, meta),
    )
