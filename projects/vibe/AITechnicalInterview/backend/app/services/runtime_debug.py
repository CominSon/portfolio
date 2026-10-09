"""Следы выполнения интервью в ai_settings для диагностики «зависаний» в реальном времени."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.entities import Interview

RUNTIME_DEBUG_KEY = "runtime_debug"

MAIN_QUESTION_READY_PHASES = frozenset(
    {
        "opening_path_done",
        "opening_turn_ready",
        "transcripts_committed",
        "tts_background_scheduled",
        "tts_cache_hit",
        "submit_answer_response",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_runtime_debug(interview: Interview) -> list[dict[str, Any]]:
    settings = interview.ai_settings if isinstance(interview.ai_settings, dict) else {}
    raw = settings.get(RUNTIME_DEBUG_KEY) or []
    return list(raw) if isinstance(raw, list) else []


async def runtime_debug_trace(
    db: AsyncSession,
    interview: Interview,
    phase: str,
    **extra: Any,
) -> None:
    settings = dict(interview.ai_settings or {})
    log = list(settings.get(RUNTIME_DEBUG_KEY) or [])
    log.append({"at": _now_iso(), "phase": phase, **extra})
    settings[RUNTIME_DEBUG_KEY] = log[-60:]
    interview.ai_settings = settings
    await db.flush()


async def runtime_debug_trace_committed(
    interview_id: uuid.UUID,
    phase: str,
    **extra: Any,
) -> None:
    """Запись фазы в отдельной транзакции — видна в runtime-debug во время долгого submit."""
    async with async_session_factory() as session:
        result = await session.execute(select(Interview).where(Interview.id == interview_id))
        interview = result.scalar_one_or_none()
        if not interview:
            return
        settings = dict(interview.ai_settings or {})
        log = list(settings.get(RUNTIME_DEBUG_KEY) or [])
        log.append({"at": _now_iso(), "phase": phase, **extra})
        settings[RUNTIME_DEBUG_KEY] = log[-60:]
        interview.ai_settings = settings
        await session.commit()


def build_runtime_debug_snapshot(interview: Interview, *, transcript_count: int = 0) -> dict[str, Any]:
    from pathlib import Path

    from app.config import get_settings
    from app.services.warmup_quiz import get_warmup_quiz, get_warmup_quiz_answers

    settings = get_settings()
    tts_dir = Path(settings.recordings_dir) / "tts"
    opening_id = f"opening-{interview.id}"
    opening_candidates = [
        tts_dir / f"{opening_id}.wav",
        tts_dir / f"{opening_id}.mp3",
    ]
    opening_ready = any(p.exists() and p.stat().st_size > 0 for p in opening_candidates)

    trace = get_runtime_debug(interview)
    last_phase = trace[-1]["phase"] if trace else None
    last_at = trace[-1].get("at") if trace else None
    main_question_ready = transcript_count >= 2 or (
        last_phase in MAIN_QUESTION_READY_PHASES if last_phase else False
    )

    return {
        "interview_id": str(interview.id),
        "status": interview.status,
        "started_at": interview.started_at.isoformat() if interview.started_at else None,
        "transcript_count": transcript_count,
        "warmup_bank": len(get_warmup_quiz(interview)),
        "warmup_answers": len(get_warmup_quiz_answers(interview)),
        "opening_tts_ready": opening_ready,
        "main_question_ready": main_question_ready,
        "last_debug_phase": last_phase,
        "last_debug_at": last_at,
        "trace": trace[-15:],
    }
