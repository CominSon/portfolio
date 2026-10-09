import asyncio
import logging
import uuid
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import require_admin
from app.api.deps import editor_manager, recording_manager, session_manager, voice_pipeline
from app.config import get_settings
from app.api.serialize import interview_to_response, report_to_response
from app.database import async_session_factory, get_db
from app.services.competency_utils import skill_to_editor_language
from app.services.email_notify import send_video_email
from app.services.transcript_export import format_transcript_txt
from app.schemas.interview import (
    CompetenciesUpdate,
    GenerateLinkRequest,
    InterviewCreate,
    InterviewFormatUpdate,
    InterviewResponse,
    MediaStatusUpdate,
    ReportResponse,
    SubmitAnswerRequest,
    WarmupQuizAnswerRequest,
)
from app.services.code_action_policy import should_skip_ai_code_action
from app.services.code_exercise import clear_exercise_baseline, get_exercise_baseline, set_exercise_baseline
from app.services.editor_snippets import fallback_editor_snippet
from app.services.editor_turn_policy import should_reset_editor_for_ai_turn, turn_continue_flags
from app.services.transcript_format import ai_transcript_with_editor_code, question_needs_editor_code
from app.services.collaborative_editor_manager import CollaborativeEditorManager
from app.services.document_analysis_manager import DocumentAnalysisManager
from app.services.interview_end import ai_signals_interview_end
from app.services.interview_montage_service import build_interview_montage
from app.services.recording_manager import RecordingManager
from app.services.recording_cleanup import cleanup_after_interview
from app.services.stt_providers import SttProviderError
from app.services.voice_pipeline import SttUnavailableError
from app.models.entities import InterviewStatus
from app.models.entities import Transcript
from app.services.runtime_debug import (
    build_runtime_debug_snapshot,
    runtime_debug_trace,
    runtime_debug_trace_committed,
)
from app.services.datetime_utils import format_moscow
from app.services.warmup_quiz import answered_warmup_signatures, get_warmup_quiz, get_warmup_quiz_public

router = APIRouter(prefix="/interviews", tags=["interviews"])
logger = logging.getLogger(__name__)
doc_manager = DocumentAnalysisManager()
_recordings = RecordingManager()


async def _synthesize_reply_audio(
    interview_id: UUID, message_id: str, text: str
) -> tuple[str | None, bool]:
    """Синтез озвучки; возвращает URL и флаг готовности файла."""
    if not text.strip() or not get_settings().tts_enabled:
        return None, False

    audio_url = f"/api/v1/interviews/{interview_id}/tts-audio/{message_id}"
    cached = voice_pipeline._resolve_tts_path(message_id)
    if cached.exists() and cached.stat().st_size > 0:
        return audio_url, True

    try:
        path = await asyncio.wait_for(
            voice_pipeline.text_to_speech(text, message_id),
            timeout=90.0,
        )
    except asyncio.TimeoutError:
        logger.warning("TTS timeout message_id=%s", message_id)
        return audio_url, False
    except Exception as exc:
        logger.warning("TTS failed message_id=%s: %s", message_id, exc)
        return audio_url, False

    ready = bool(path and path.exists() and path.stat().st_size > 0)
    return audio_url, ready


async def _ensure_reply_audio_ready(
    interview_id: UUID,
    message_id: str,
    text: str,
    *,
    attempts: int = 3,
) -> tuple[str | None, bool]:
    """Дождаться готовой озвучки (несколько попыток). Без фоновых «audio_ready=false»."""
    if not text.strip():
        return None, False
    settings = get_settings()
    if not settings.tts_enabled:
        return None, False

    audio_url = f"/api/v1/interviews/{interview_id}/tts-audio/{message_id}"
    for attempt in range(1, attempts + 1):
        url, ready = await _synthesize_reply_audio(interview_id, message_id, text)
        if ready:
            return url, True
        logger.warning(
            "TTS not ready interview=%s message_id=%s attempt=%s/%s",
            interview_id,
            message_id,
            attempt,
            attempts,
        )
    return audio_url, False


async def _background_tts(interview_id: UUID, message_id: str, text: str) -> None:
    try:
        await _synthesize_reply_audio(interview_id, message_id, text)
    except Exception:
        logger.warning("background TTS failed message_id=%s", message_id, exc_info=True)


def _is_sqlite_locked(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database locked" in msg


def _briefing_audio_url_if_ready(interview) -> str | None:
    settings = dict(interview.ai_settings or {})
    message_id = settings.get("briefing_message_id") or f"briefing-{interview.id}"
    cached = voice_pipeline._resolve_tts_path(str(message_id))
    if cached.exists() and cached.stat().st_size > 0:
        return f"/api/v1/interviews/{interview.id}/tts-audio/{message_id}"
    return None


async def _prepare_interview_session(interview_id: UUID) -> None:
    """Фоновая подготовка озвучки приветствия и банка мини-вопросов (не блокирует админку)."""
    try:
        async with async_session_factory() as db:
            interview = await session_manager.get_interview(db, interview_id)
            if not interview:
                return
            await session_manager.ensure_briefing(db, interview)
            if not get_warmup_quiz(interview):
                await session_manager.ensure_warmup_quiz(db, interview)
            await db.commit()
        logger.info("session assets ready interview=%s", interview_id)
    except Exception:
        logger.exception("session prep failed interview=%s", interview_id)


def _completion_recipients(interview) -> list[str]:
    """Только feedback_emails работодателя/HR — кандидату отчёт не шлём."""
    emails = [str(e).strip() for e in (interview.feedback_emails or []) if e]
    return list(dict.fromkeys(emails))


def _report_payload(interview) -> tuple[dict, dict]:
    from app.services.resume_analyzer import candidate_display_name

    report_data = {}
    if interview.report:
        report_data = {
            "competency_scores": interview.report.competency_scores or {},
            "strengths": interview.report.strengths or [],
            "weaknesses": interview.report.weaknesses or [],
            "communication_assessment": interview.report.communication_assessment or {},
            "code_quality_assessment": interview.report.code_quality_assessment or {},
            "honesty_signals": interview.report.honesty_signals or {},
            "confidence_level": interview.report.confidence_level,
            "recommendation": interview.report.recommendation,
            "final_summary": interview.report.final_summary or "",
        }
    interview_meta = {
        "candidate_name": candidate_display_name(interview),
        "format": interview.selected_format,
        "editor_language": interview.editor_language,
        "started_at": format_moscow(interview.started_at),
        "ended_at": format_moscow(interview.ended_at),
    }
    return report_data, interview_meta


async def _background_finalize_interview_and_email(interview_id: UUID) -> None:
    """Единый финальный поток: отчёт + монтаж + одно письмо с итогами и ссылками."""
    async with async_session_factory() as db:
        try:
            interview = await session_manager.get_interview(db, interview_id)
            if not interview:
                return
            # Если кандидат много рассуждал во время кодинга, но редко нажимал «Ответить»,
            # то часть речи не попадёт в стенограмму. Попробуем дополнить её STT по полной
            # аудиодорожке (recordings/<id>/audio/recording.webm) перед построением отчёта.
            settings = get_settings()
            if getattr(settings, "transcribe_full_session_audio", False):
                audio_path = _recordings.recording_path(interview_id, "audio")
                if audio_path.is_file() and audio_path.stat().st_size > 200:
                    # В faster-whisper нет простого лимита по секундам без таймстемпов,
                    # поэтому лимит ниже мягкий: только если файл не слишком большой.
                    # (1–10 мин речи обычно укладываются по размеру в webm/opus).
                    try:
                        full_text = await voice_pipeline.speech_to_text_from_path(str(audio_path))
                        full_text = (full_text or "").strip()
                        if full_text:
                            await session_manager.transcript_manager.add_entry(
                                db,
                                interview.id,
                                "system",
                                "[Авто-стенограмма всей аудиодорожки]\n" + full_text,
                            )
                            await db.commit()
                    except Exception:
                        logger.warning("full session STT failed interview=%s", interview_id, exc_info=True)
            # 1) Формируем отчёт
            await session_manager.complete_interview(db, interview)
            await db.commit()
            await db.refresh(interview, attribute_names=["report", "candidate"])

            # 2) Готовим данные для единого письма
            recipients = _completion_recipients(interview)
            if not recipients:
                logger.warning("no email recipients interview=%s", interview_id)
                cleanup_after_interview(interview_id)
                return
            report_data, interview_meta = _report_payload(interview)

            # 3) Пытаемся собрать видео (может быть долго)
            montage_path = await build_interview_montage(db, interview_id)
            if montage_path:
                ok = send_video_email(
                    recipients,
                    interview_id,
                    interview_meta,
                    report_data=report_data if report_data else None,
                )
                if not ok:
                    logger.error(
                        "final email NOT sent interview=%s recipients=%s",
                        interview_id,
                        recipients,
                    )
            else:
                # Даже если монтаж ещё не готов — отправляем одно письмо с итогами и ссылками.
                ok = send_video_email(
                    recipients,
                    interview_id,
                    interview_meta,
                    report_data=report_data if report_data else None,
                )
                if not ok:
                    logger.error("final email (without montage) NOT sent interview=%s", interview_id)

            cleanup_after_interview(interview_id)
        except Exception:
            logger.exception("background finalize failed interview=%s", interview_id)
            await db.rollback()


def _apply_focus_editor_language(interview, turn: dict) -> None:
    focus = (turn.get("competency_focus") or "").strip()
    if not focus:
        return
    lang = skill_to_editor_language(focus)
    if lang != interview.editor_language:
        interview.editor_language = lang


@router.post("", response_model=InterviewResponse)
async def create_interview(
    data: InterviewCreate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    interview = await session_manager.create_interview(db, data)
    return await interview_to_response(db, interview)


_CLOSED_STATUSES = frozenset(
    {
        "completing",
        "completed",
        "report_ready",
    }
)


@router.get("/join/{token}", response_model=InterviewResponse)
async def join_interview(
    token: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    interview = await session_manager.get_by_token(db, token)
    if not interview:
        raise HTTPException(404, "Interview not found")
    if interview.status in _CLOSED_STATUSES:
        raise HTTPException(
            410,
            detail="Интервью завершено. Ссылка больше не действует.",
        )
    await session_manager.mark_candidate_joined(interview)
    await session_manager.sync_sql_dialect(interview)
    briefing_text, briefing_audio_url = await session_manager.ensure_briefing(db, interview)
    warmup_quiz = get_warmup_quiz_public(interview)
    if not warmup_quiz:
        background_tasks.add_task(_prepare_interview_session, interview.id)
    await db.commit()
    return await interview_to_response(
        db,
        interview,
        include_session=True,
        briefing_text=briefing_text,
        briefing_audio_url=briefing_audio_url,
        warmup_quiz=warmup_quiz,
    )


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    return await interview_to_response(
        db,
        interview,
        briefing_audio_url=_briefing_audio_url_if_ready(interview),
    )


@router.post("/{interview_id}/documents")
async def upload_documents(
    interview_id: UUID,
    job_description: UploadFile | None = File(None),
    resume: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    if job_description:
        data = await job_description.read()
        try:
            interview.job_description_text = doc_manager.extract_text(
                job_description.filename or "jd.pdf", data
            )
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
    if resume:
        data = await resume.read()
        try:
            text = doc_manager.extract_text(resume.filename or "resume.pdf", data)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        interview.resume_text = text
        from sqlalchemy import select
        from app.models.entities import Candidate
        if interview.candidate_id:
            result = await db.execute(select(Candidate).where(Candidate.id == interview.candidate_id))
            cand = result.scalar_one_or_none()
            if cand:
                cand.resume_text = text
    interview.status = "documents_uploaded"
    if (interview.resume_text or "").strip():
        try:
            await session_manager.ensure_resume_profile(db, interview)
        except Exception:
            logger.exception("resume profile analysis failed interview=%s", interview_id)
    from app.services.sql_dialect import sync_interview_sql_dialect_async

    orch = session_manager.document_analysis.competency_analyzer.orchestrator
    await sync_interview_sql_dialect_async(interview, orchestrator=orch)
    await db.commit()
    return {"status": interview.status}


@router.post("/{interview_id}/analyze-documents")
async def analyze_documents(
    interview_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    try:
        proposed = await session_manager.analyze_documents(db, interview)
    except ValueError as e:
        raise HTTPException(400, detail=str(e)) from e
    return {"proposed_competencies": proposed}


@router.put("/{interview_id}/competencies")
async def update_competencies(
    interview_id: UUID,
    data: CompetenciesUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    await session_manager.update_competencies(db, interview, data.competencies)
    return {"status": interview.status}


@router.put("/{interview_id}/format")
async def update_format(
    interview_id: UUID,
    data: InterviewFormatUpdate,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    from app.services.interview_formats import (
        LEGACY_AI_ASSISTED_FORMAT,
        get_live_coding_ai_assistant,
        get_session_mode,
        interview_test_max_turns,
        is_live_coding_format,
        normalize_format_list,
        set_live_coding_ai_assistant,
        set_session_mode,
    )

    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    interview.format_selection_mode = data.format_selection_mode
    interview.allowed_formats = normalize_format_list(data.allowed_formats)

    ai_assistant = data.live_coding_ai_assistant
    manual_fmt = data.selected_format
    if manual_fmt == LEGACY_AI_ASSISTED_FORMAT:
        manual_fmt = "Live Coding"
        ai_assistant = True

    if data.format_selection_mode in ("auto", "restricted"):
        fmt = await session_manager.select_format(db, interview)
    else:
        interview.status = "format_selected"
        fmt = manual_fmt or interview.selected_format
        if fmt:
            interview.selected_format = fmt

    if ai_assistant:
        interview.allowed_formats = ["Live Coding"]
        interview.selected_format = "Live Coding"
        set_live_coding_ai_assistant(interview, True)
    elif is_live_coding_format(interview.selected_format):
        set_live_coding_ai_assistant(interview, ai_assistant)
    else:
        set_live_coding_ai_assistant(interview, False)

    set_session_mode(interview, data.session_mode, test_max_turns=data.test_max_turns)

    await db.commit()
    return {
        "selected_format": interview.selected_format,
        "status": interview.status,
        "live_coding_ai_assistant": get_live_coding_ai_assistant(interview),
        "session_mode": get_session_mode(interview),
        "test_max_turns": interview_test_max_turns(interview)
        if get_session_mode(interview) == "test"
        else None,
        "duration_minutes": interview.duration_minutes,
    }


@router.post("/{interview_id}/generate-link")
async def generate_link(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    data: GenerateLinkRequest | None = None,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    origin = (data.frontend_origin.strip().rstrip("/") if data and data.frontend_origin else None)
    link = await session_manager.generate_link(interview, base_url=origin)

    from app.services.tts_prepare import briefing_text as build_briefing_text

    briefing_text = build_briefing_text(get_settings().effective_tts_voice)
    briefing_audio_url = _briefing_audio_url_if_ready(interview)
    quiz_count = len(get_warmup_quiz(interview))
    needs_prep = briefing_audio_url is None or quiz_count == 0

    if needs_prep:
        background_tasks.add_task(_prepare_interview_session, interview_id)

    await db.commit()
    return {
        "candidate_link": link,
        "access_token": interview.access_token,
        "briefing_text": briefing_text,
        "briefing_audio_url": briefing_audio_url,
        "warmup_quiz_count": quiz_count,
        "warmup_quiz_ready": quiz_count > 0,
        "preparing": needs_prep,
        "candidate_name": (await interview_to_response(db, interview)).candidate_name,
    }


@router.post("/{interview_id}/clone-for-candidate", response_model=InterviewResponse)
async def clone_for_candidate(
    interview_id: UUID,
    candidate_name: str | None = Form(None),
    resume_filename: str | None = Form(None),
    resume: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(require_admin),
):
    """Клон интервью для другого кандидата (та же вакансия, скиллы, формат)."""
    source = await session_manager.get_interview(db, interview_id)
    if not source:
        raise HTTPException(404, "Interview not found")
    if not (source.job_description_text or "").strip():
        raise HTTPException(400, detail="У исходного интервью нет текста вакансии")
    # competencies уже подгружены через selectinload в get_interview
    if not list(source.competencies or []):
        raise HTTPException(400, detail="Сначала подтвердите языки/навыки")

    resume_text: str | None = None
    fname = (resume_filename or "").strip() or None
    if resume is not None:
        data = await resume.read()
        fname = fname or (resume.filename or None)
        try:
            resume_text = doc_manager.extract_text(resume.filename or "resume.pdf", data)
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc

    name = (candidate_name or "").strip() or None
    if not resume_text and not name and not fname:
        raise HTTPException(400, detail="Укажите ФИО кандидата или загрузите резюме")

    from app.services.candidate_name import resolve_candidate_name

    resolved_name = resolve_candidate_name(
        manual_name=name,
        resume_text=resume_text,
        resume_filename=fname,
    )

    try:
        interview = await session_manager.clone_for_candidate(
            db,
            source,
            candidate_name=resolved_name or name,
            resume_text=resume_text,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("clone-for-candidate failed source=%s", interview_id)
        raise HTTPException(500, detail="Не удалось создать интервью для кандидата") from None
    return await interview_to_response(db, interview)


@router.post("/{interview_id}/media-status")
async def media_status(interview_id: UUID, data: MediaStatusUpdate, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    await session_manager.update_media(
        db, interview, data.camera_enabled, data.microphone_enabled, data.screenshare_enabled
    )
    return {
        "status": interview.status,
        "media_ready": session_manager.media_ready(interview),
    }


@router.get("/{interview_id}/warmup-quiz")
async def get_warmup_quiz_endpoint(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    from app.services.warmup_quiz import scrub_warmup_quiz_quality

    scrub_warmup_quiz_quality(interview)
    await db.commit()
    return {
        "ready": bool(get_warmup_quiz(interview)),
        "questions": get_warmup_quiz_public(interview),
        "answered_signatures": answered_warmup_signatures(interview),
    }


@router.post("/{interview_id}/warmup-quiz/refill")
async def refill_warmup_quiz_endpoint(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    if interview.status not in (
        InterviewStatus.ACTIVE.value,
        InterviewStatus.PAUSED.value,
        InterviewStatus.READY.value,
        InterviewStatus.CANDIDATE_JOINED.value,
    ):
        raise HTTPException(400, detail="Догрузка недоступна для текущего статуса интервью")
    result = await session_manager.refill_warmup_quiz(db, interview)
    await db.commit()
    return result


@router.post("/{interview_id}/warmup-quiz/answer")
async def submit_warmup_quiz_answer(
    interview_id: UUID,
    data: WarmupQuizAnswerRequest,
):
    last_exc: Exception | None = None
    for attempt in range(8):
        try:
            async with async_session_factory() as db:
                interview = await session_manager.get_interview(db, interview_id)
                if not interview:
                    raise HTTPException(404, "Interview not found")
                result = await session_manager.submit_warmup_quiz_answer(
                    db,
                    interview,
                    data.question_id,
                    data.selected_index,
                    timed_out=data.timed_out,
                )
                await db.commit()
                return result
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        except Exception as exc:
            last_exc = exc
            if _is_sqlite_locked(exc) and attempt < 7:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            logger.exception("warmup quiz answer failed interview=%s", interview_id)
            raise HTTPException(
                503,
                detail="Сервер занят (база данных). Нажмите вариант ответа ещё раз.",
            ) from exc
    raise HTTPException(503, detail="Сервер занят. Повторите ответ.") from last_exc


@router.post("/{interview_id}/warmup-quiz/skip")
async def skip_warmup_quiz_question(
    interview_id: UUID,
    data: WarmupQuizAnswerRequest,
):
    """Пропуск мини-вопроса при сбое отправки — не учитывается в итоговой оценке."""
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            async with async_session_factory() as db:
                interview = await session_manager.get_interview(db, interview_id)
                if not interview:
                    raise HTTPException(404, "Interview not found")
                result = await session_manager.skip_warmup_quiz_question(
                    db,
                    interview,
                    data.question_id,
                    reason="submit_failed",
                )
                await db.commit()
                return result
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
        except Exception as exc:
            last_exc = exc
            if _is_sqlite_locked(exc) and attempt < 4:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            logger.exception("warmup quiz skip failed interview=%s", interview_id)
            raise HTTPException(503, detail="Сервер занят. Повторите позже.") from exc
    raise HTTPException(503, detail="Сервер занят.") from last_exc


@router.post("/{interview_id}/opening-turn")
async def create_opening_turn(
    interview_id: UUID,
):
    """Первый вопрос: транскрипт + готовая озвучка (мини-тест идёт параллельно на клиенте)."""
    await runtime_debug_trace_committed(interview_id, "opening_turn_enter")

    async with async_session_factory() as db:
        interview = await session_manager.get_interview(db, interview_id)
        if not interview:
            raise HTTPException(404, "Interview not found")
        if interview.status not in (
            InterviewStatus.ACTIVE.value,
            InterviewStatus.READY.value,
            InterviewStatus.CANDIDATE_JOINED.value,
        ):
            raise HTTPException(400, detail="Интервью не в статусе для старта")

        try:
            turn = await session_manager.process_candidate_answer(
                db, interview, "[Interview started]", "voice"
            )
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc

        await db.commit()
        message_id = str(turn.get("message_id") or f"opening-{interview_id}")
        ai_text = turn.get("message", "") or ""
        editor_content = interview.editor_content
        editor_language = interview.editor_language

    settings = get_settings()
    audio_url = (
        f"/api/v1/interviews/{interview_id}/tts-audio/{message_id}"
        if ai_text.strip() and settings.tts_enabled
        else None
    )
    audio_ready = False
    if ai_text.strip() and settings.tts_enabled:
        audio_url, audio_ready = await _ensure_reply_audio_ready(
            interview_id, message_id, ai_text, attempts=3
        )
        if not audio_ready:
            raise HTTPException(
                503,
                detail="Не удалось подготовить озвучку первого вопроса. Проверьте TTS (Silero/edge) на сервере.",
            )
    elif ai_text.strip():
        audio_ready = True

    await runtime_debug_trace_committed(
        interview_id,
        "opening_turn_ready",
        message_id=message_id,
        audio_ready=audio_ready,
        message_chars=len(ai_text),
    )

    return {
        "ai_message": ai_text,
        "message_id": message_id,
        "audio_url": audio_url,
        "audio_ready": audio_ready,
        "editor_content": editor_content,
        "editor_language": editor_language,
        "should_end_interview": False,
    }


@router.post("/{interview_id}/start")
async def start_interview(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    if not session_manager.media_ready(interview):
        raise HTTPException(400, detail={"code": "MEDIA_REQUIRED", "message": "Enable camera, mic, and screen share"})
    await session_manager.start_interview(db, interview)
    return {"status": interview.status}


@router.get("/{interview_id}/runtime-debug")
async def get_runtime_debug(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    """Диагностика «на лету»: фазы submit-answer, транскрипт, мини-тест, TTS первого вопроса."""
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    tx_count = (
        await db.execute(
            select(func.count()).select_from(Transcript).where(Transcript.interview_id == interview_id)
        )
    ).scalar_one()
    return build_runtime_debug_snapshot(interview, transcript_count=int(tx_count or 0))


@router.post("/{interview_id}/submit-answer")
async def submit_answer(
    interview_id: UUID,
    data: SubmitAnswerRequest,
):
    await runtime_debug_trace_committed(interview_id, "submit_answer_enter")

    async with async_session_factory() as db:
        interview = await session_manager.get_interview(db, interview_id)
        if not interview:
            raise HTTPException(404, "Interview not found")
        text = data.text or ""
        await runtime_debug_trace(
            db,
            interview,
            "submit_answer_start",
            answer_type=data.answer_type,
            text_preview=(text or "")[:120],
        )
        code_before_submit = (interview.editor_content or "").strip()
        if data.editor_content is not None:
            interview.editor_content = data.editor_content
            interview.editor_version += 1
            await db.commit()
            await db.refresh(interview)

        if not text and data.answer_type == "code":
            text = f"[Code submission]\n{interview.editor_content}"

        if not get_exercise_baseline(interview) and code_before_submit:
            set_exercise_baseline(interview, code_before_submit)

        try:
            turn = await session_manager.process_candidate_answer(db, interview, text, data.answer_type)
            await runtime_debug_trace(
                db,
                interview,
                "turn_built",
                message_id=str(turn.get("message_id") or ""),
                message_chars=len(str(turn.get("message") or "")),
            )
        except ValueError as exc:
            await runtime_debug_trace(db, interview, "submit_rejected", error=str(exc))
            logger.warning("submit_answer rejected: %s", exc)
            raise HTTPException(400, detail=str(exc)) from exc
        except Exception as exc:
            await runtime_debug_trace(db, interview, "submit_failed", error=str(exc)[:200])
            logger.exception("submit_answer failed interview=%s", interview_id)
            raise HTTPException(500, detail=f"Interview turn failed: {exc}") from exc

        ai_text = turn.get("message", "") or ""
        code_actions = turn.get("code_actions") or []
        cont_flag, keep_flag = turn_continue_flags(turn)
        reset_editor = should_reset_editor_for_ai_turn(
            message=ai_text,
            code_actions=code_actions,
            competency_focus=turn.get("competency_focus"),
            current_editor_language=interview.editor_language or "python",
            format_name=interview.selected_format or "",
            continue_exercise=cont_flag,
            keep_editor=keep_flag,
        )
        if reset_editor:
            interview.editor_content = ""
            interview.editor_version += 1
            clear_exercise_baseline(interview)
            logger.info("editor reset before AI code_actions interview=%s", interview_id)
        else:
            # Follow-up «перепишите тот же запрос» — вернуть код, если редактор пуст
            baseline_now = get_exercise_baseline(interview).strip()
            if not (interview.editor_content or "").strip() and baseline_now:
                interview.editor_content = baseline_now
                interview.editor_version += 1
                logger.info("editor restored from baseline (continue) interview=%s", interview_id)

        code_actions_applied = 0
        for action in code_actions:
            op = action.get("action", "insert")
            if op not in ("insert", "replace", "delete"):
                continue
            if should_skip_ai_code_action(action, interview, code_before_submit, data.answer_type):
                logger.info("code_action skipped (revert/no-op): action=%s", op)
                continue
            op_type = f"code_{op}"
            try:
                await editor_manager.apply_and_persist(
                    db,
                    interview,
                    "ai",
                    op_type,
                    action.get("range", {"startLine": 1, "startColumn": 1, "endLine": 1, "endColumn": 1}),
                    action.get("text", "") or "",
                )
                code_actions_applied += 1
                if op == "replace":
                    set_exercise_baseline(interview, action.get("text") or "")
            except Exception as exc:
                logger.warning("code_action skipped: %s", exc)

        _apply_focus_editor_language(interview, turn)

        # Если обещали код в редакторе, но сниппет не применился — подставляем запасной шаблон
        if (
            reset_editor
            and code_actions_applied == 0
            and question_needs_editor_code(ai_text, format_name=interview.selected_format or "")
        ):
            snippet = fallback_editor_snippet(
                interview,
                competency_focus=turn.get("competency_focus"),
                ai_text=ai_text,
            )
            if snippet.strip():
                interview.editor_content = snippet
                interview.editor_version += 1
                set_exercise_baseline(interview, snippet)
                code_actions_applied = 1
                logger.info("editor fallback snippet applied interview=%s", interview_id)
            else:
                interview.editor_content = ""
                interview.editor_version += 1
                clear_exercise_baseline(interview)

        ai_transcript = ai_transcript_with_editor_code(
            ai_text,
            interview.editor_content,
            format_name=interview.selected_format or "",
            code_actions=code_actions,
        )
        await session_manager.transcript_manager.add_entry(db, interview.id, "ai", ai_transcript)

        await db.commit()
        await db.refresh(interview)

        raw_id = turn.get("message_id")
        message_id = str(raw_id) if raw_id else str(uuid.uuid4())
        editor_content = interview.editor_content
        editor_language = interview.editor_language
        should_end = ai_signals_interview_end(
            ai_text,
            turn_end_flag=bool(turn.get("end_interview")),
        )

    settings = get_settings()
    audio_url = (
        f"/api/v1/interviews/{interview_id}/tts-audio/{message_id}"
        if ai_text.strip() and settings.tts_enabled
        else None
    )
    audio_ready = False
    if ai_text.strip() and settings.tts_enabled:
        audio_url, audio_ready = await _ensure_reply_audio_ready(
            interview_id, message_id, ai_text, attempts=3
        )
        if not audio_ready:
            raise HTTPException(
                503,
                detail="Не удалось подготовить озвучку ответа интервьюера.",
            )
    elif ai_text.strip():
        audio_ready = True

    await runtime_debug_trace_committed(
        interview_id,
        "submit_answer_response",
        audio_ready=audio_ready,
        message_id=message_id,
    )

    return {
        "ai_message": ai_text,
        "message_id": message_id,
        "code_actions_applied": code_actions_applied,
        "editor_content": editor_content,
        "editor_language": editor_language,
        "audio_url": audio_url,
        "audio_ready": audio_ready,
        "should_end_interview": should_end,
        "turn": turn,
    }


@router.post("/{interview_id}/stt")
async def speech_to_text(interview_id: UUID, audio: UploadFile = File(...)):
    _ = interview_id
    data = await audio.read()
    fname = audio.filename or "answer.webm"
    if len(data) < 200:
        raise HTTPException(400, detail="Слишком короткая аудиозапись. Говорите дольше перед «Ответить».")
    settings = get_settings()
    provider = (settings.stt_provider or "").lower()
    if provider in ("openai", "yandex"):
        timeout = 300.0
    else:
        timeout = 90.0
    try:
        text = await asyncio.wait_for(
            voice_pipeline.speech_to_text(data, filename=fname),
            timeout=timeout,
        )
    except ValueError as exc:
        raise HTTPException(413, detail=str(exc)) from exc
    except (SttUnavailableError, SttProviderError) as exc:
        raise HTTPException(503, detail=str(exc)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            504,
            detail=(
                "Распознавание речи заняло слишком долго. "
                "Отредактируйте текст в окне проверки или сократите ответ."
            ),
        ) from exc
    if not text.strip():
        if len(data) >= 800:
            return {
                "text": "",
                "warning": (
                    "Речь не распознана при достаточном объёме аудио. "
                    "Говорите громче и ближе к микрофону или допишите ответ в редакторе."
                ),
            }
        raise HTTPException(
            422,
            detail="Речь не распознана. Говорите 3–5 секунд громче или допишите ответ в редакторе.",
        )
    return {"text": text}


@router.get("/{interview_id}/tts")
async def text_to_speech(interview_id: UUID, text: str):
    path = await voice_pipeline.text_to_speech(text, f"{interview_id}-tts")
    if not path:
        raise HTTPException(503, detail="Синтез речи недоступен (проверьте TTS_ENGINE и зависимости)")
    return FileResponse(path, media_type=voice_pipeline.media_type_for(path))


def _tts_audio_path(message_id: str) -> Path | None:
    from app.config import get_settings

    tts_dir = Path(get_settings().recordings_dir) / "tts"
    for name in (f"{message_id}.wav", f"{message_id}.mp3", f"{message_id}.ogg"):
        path = tts_dir / name
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


@router.get("/{interview_id}/tts-audio/{message_id}")
@router.head("/{interview_id}/tts-audio/{message_id}")
async def get_tts_audio(interview_id: UUID, message_id: str):
    from app.services.voice_pipeline import VoicePipeline

    path = _tts_audio_path(message_id)
    if not path:
        raise HTTPException(404, "Audio not found")
    media_type = VoicePipeline.media_type_for(path)
    return FileResponse(path, media_type=media_type)


@router.get("/{interview_id}/recordings/{stream_type}")
async def download_recording(
    interview_id: UUID,
    stream_type: str,
    db: AsyncSession = Depends(get_db),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")

    if stream_type == "montage":
        from app.services.interview_montage_service import mp4_looks_complete

        path = recording_manager.montage_path(interview_id)
        if not mp4_looks_complete(path):
            raise HTTPException(404, "Итоговое видео ещё не готово или файл повреждён")
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=f"interview_{interview_id}.mp4",
        )

    if stream_type not in ("camera", "screen"):
        raise HTTPException(400, detail="stream_type: camera, screen или montage")
    path = recording_manager.recording_path(interview_id, stream_type)
    if not path.is_file() or path.stat().st_size == 0:
        raise HTTPException(404, "Запись не найдена")
    return FileResponse(path, media_type="video/webm", filename=f"{stream_type}_{interview_id}.webm")


@router.post("/{interview_id}/recordings/chunk")
async def upload_recording_chunk(
    interview_id: UUID,
    stream_type: str,
    chunk_index: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    data = await file.read()
    meta = await recording_manager.save_chunk(db, interview_id, stream_type, chunk_index, data)
    return {"stream_type": meta.stream_type, "chunk_count": meta.chunk_count}


@router.post("/{interview_id}/complete")
async def complete_interview(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    interview.status = "completing"
    await db.commit()
    settings = get_settings()
    if settings.smtp_host and settings.smtp_password:
        farewell = (
            "Спасибо за интервью! Отчёт формируется и будет отправлен "
            "на почту, указанную при создании сессии."
        )
    else:
        farewell = (
            "Спасибо за интервью! Отчёт формируется — "
            "работодатель получит его в админке платформы."
        )
    mid = f"farewell-{interview_id}"
    audio_url = (
        f"/api/v1/interviews/{interview_id}/tts-audio/{mid}"
        if get_settings().tts_enabled
        else None
    )
    if audio_url:
        background_tasks.add_task(_background_tts, interview_id, mid, farewell)
    background_tasks.add_task(_background_finalize_interview_and_email, interview_id)
    return {
        "status": "completing",
        "farewell_message": farewell,
        "audio_url": audio_url,
        "audio_ready": False,
    }


@router.get("/{interview_id}/report", response_model=ReportResponse)
async def get_report(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview or not interview.report:
        raise HTTPException(404, "Report not found")
    return await report_to_response(db, interview.report, interview=interview)


@router.get("/{interview_id}/transcript.txt")
async def download_transcript_txt(interview_id: UUID, db: AsyncSession = Depends(get_db)):
    interview = await session_manager.get_interview(db, interview_id)
    if not interview:
        raise HTTPException(404, "Interview not found")
    history = await session_manager.transcript_manager.get_history(db, interview_id, limit=500)
    txt = format_transcript_txt(history)
    return Response(
        content=txt,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="transcript_{interview_id}.txt"'},
    )
