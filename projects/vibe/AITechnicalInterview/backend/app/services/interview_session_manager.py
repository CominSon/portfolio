import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Candidate, Competency, Interview, InterviewStatus
from app.schemas.common import CompetencyItem
from app.schemas.interview import InterviewCreate
from app.services.llm_orchestrator import InterviewContext, LlmOrchestrator
from app.services.voice_pipeline import VoicePipeline
from app.services.ai_turn_normalize import normalize_ai_turn
from app.services.code_exercise import (
    build_code_change_notice,
    clear_exercise_baseline,
    get_exercise_baseline,
    set_exercise_baseline,
)
from app.services.interview_dialog_policy import (
    apply_dialog_policy_to_turn,
    build_dialog_directives,
    candidate_answer_is_substantive,
)
from app.services.competency_plan import (
    difficulty_for_levels,
    preferred_competency,
    record_skill_coverage,
    skill_plan_prompt_block,
    untested_skills,
)
from app.services.interview_progress import (
    asked_questions_block,
    bump_after_answer,
    get_progress,
    is_generic_ai_message,
    register_ai_question,
    save_progress,
)
from app.services.competency_utils import normalize_weights, primary_editor_language
from app.services.interview_formats import (
    LEGACY_AI_ASSISTED_FORMAT,
    get_live_coding_ai_assistant,
    normalize_format_list,
)
from app.services.document_analysis_manager import DocumentAnalysisManager
from app.services.report_builder import ReportBuilder
from app.services.template_manager import TemplateManager
from app.services.transcript_manager import TranscriptManager
from app.services.resume_analyzer import get_resume_profile, set_resume_profile
from app.services.runtime_debug import runtime_debug_trace
from app.services.tts_prepare import briefing_text, is_female_voice, opening_turn_text
from app.services.interview_skills import filter_resume_profile_for_competencies
from app.services.sql_dialect import get_interview_sql_dialect, sync_interview_sql_dialect_async
from app.services.transcript_format import ai_transcript_with_editor_code
from app.config import get_settings
from app.services.warmup_quiz import (
    WARMUP_QUIZ_INITIAL_COUNT,
    WARMUP_QUIZ_REFILL_BATCH,
    append_warmup_questions,
    existing_questions_hint,
    get_warmup_quiz,
    rebalance_warmup_option_order,
    scrub_warmup_quiz_quality,
    warmup_needs_rebalance,
    get_warmup_quiz_public,
    record_warmup_quiz_answer,
    record_warmup_quiz_skip,
    set_warmup_quiz,
    warmup_quiz_summary_for_prompt,
)
from app.services.datetime_utils import ensure_utc
from app.services.voice_pipeline import VoicePipeline

logger = logging.getLogger(__name__)

_DIFFICULTY_RANK = {"easy": 0, "medium": 1, "hard": 2}

_ACTIVE_STATUSES = frozenset(
    {
        InterviewStatus.ACTIVE.value,
        InterviewStatus.PAUSED.value,
        InterviewStatus.COMPLETING.value,
    }
)


STT_QUALITY_NOTE = (
    "Устная часть ответа — автоматическая транскрипция (STT). Возможны искажения терминов, "
    "пропуски фраз при долгом рассуждении или одновременной работе с кодом. Оценивайте смысл с поправкой."
)


class InterviewSessionManager:
    def __init__(self, voice_pipeline: VoicePipeline | None = None) -> None:
        self.document_analysis = DocumentAnalysisManager()
        self.orchestrator = LlmOrchestrator()
        self.template_manager = TemplateManager()
        self.transcript_manager = TranscriptManager()
        self.report_builder = ReportBuilder()
        self.voice = voice_pipeline or VoicePipeline()

    async def _sync_sql_dialect(self, interview: Interview) -> str | None:
        orch = self.document_analysis.competency_analyzer.orchestrator
        return await sync_interview_sql_dialect_async(interview, orchestrator=orch)

    async def sync_sql_dialect(self, interview: Interview) -> str | None:
        return await self._sync_sql_dialect(interview)

    async def create_interview(self, db: AsyncSession, data: InterviewCreate) -> Interview:
        email = (str(data.candidate_email).strip().lower() if data.candidate_email else "")
        if not email:
            email = f"anonymous-{secrets.token_hex(8)}@interview.local"
        manual_name = (data.candidate_name or "").strip() or None
        if manual_name and len(manual_name) > 255:
            manual_name = manual_name[:255]
        candidate = Candidate(email=email, name=manual_name)
        db.add(candidate)
        await db.flush()

        feedback = [e.strip().lower() for e in data.feedback_emails if e and str(e).strip()]
        interview = Interview(
            employer_id=data.employer_id,
            candidate_id=candidate.id,
            template_id=data.template_id,
            access_token=secrets.token_urlsafe(32),
            job_description_text=data.job_description_text,
            resume_text=data.resume_text,
            feedback_emails=feedback,
            status=InterviewStatus.CREATED.value,
        )
        db.add(interview)
        await db.flush()

        if data.template_id:
            template = await self.template_manager.get(db, data.template_id)
            if template:
                await self.template_manager.apply_to_interview(db, interview, template)
                for tc in template.competencies:
                    db.add(
                        Competency(
                            interview_id=interview.id,
                            skill=tc.skill,
                            level=tc.level,
                            weight=tc.weight,
                            source=tc.source,
                            confirmed=True,
                        )
                    )
                interview.status = InterviewStatus.COMPETENCIES_CONFIRMED.value

        if data.job_description_text and data.resume_text:
            interview.status = InterviewStatus.DOCUMENTS_UPLOADED.value

        await self._sync_sql_dialect(interview)
        return interview

    async def get_interview(self, db: AsyncSession, interview_id: uuid.UUID) -> Interview | None:
        result = await db.execute(
            select(Interview)
            .where(Interview.id == interview_id)
            .options(
                selectinload(Interview.competencies),
                selectinload(Interview.report),
                selectinload(Interview.candidate),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token(self, db: AsyncSession, token: str) -> Interview | None:
        result = await db.execute(
            select(Interview)
            .where(Interview.access_token == token)
            .options(
                selectinload(Interview.competencies),
                selectinload(Interview.report),
                selectinload(Interview.candidate),
            )
        )
        return result.scalar_one_or_none()

    async def ensure_resume_profile(self, db: AsyncSession, interview: Interview) -> dict | None:
        """LLM-анализ резюме (один раз на интервью): имя, навыки, персональный первый вопрос."""
        existing = get_resume_profile(interview)
        if existing and existing.get("opening_question"):
            await runtime_debug_trace(db, interview, "resume_profile_cache_hit")
            return existing
        resume = (interview.resume_text or "").strip()
        if not resume:
            return None
        # Не трогаем relationship через lazy-load (MissingGreenlet в async)
        await db.refresh(interview, attribute_names=["competencies"])
        skills = [c.skill for c in list(interview.competencies or [])]
        await runtime_debug_trace(db, interview, "resume_profile_llm_start")
        try:
            profile = await asyncio.wait_for(
                self.document_analysis.analyze_resume(
                    resume,
                    job_description=interview.job_description_text,
                    competency_skills=skills,
                ),
                timeout=90.0,
            )
        except asyncio.TimeoutError:
            await runtime_debug_trace(db, interview, "resume_profile_llm_timeout")
            logger.warning("resume profile LLM timeout interview=%s", interview.id)
            return None
        if not profile:
            return None
        set_resume_profile(interview, profile)
        await self._sync_sql_dialect(interview)
        full_name = (profile.get("candidate_full_name") or "").strip()
        first = (profile.get("candidate_first_name") or "").strip()
        display_name = full_name or first
        if display_name and interview.candidate_id:
            result = await db.execute(select(Candidate).where(Candidate.id == interview.candidate_id))
            cand = result.scalar_one_or_none()
            if cand:
                # Резюме приоритетнее ручного ФИО
                cand.name = display_name[:255]
        await db.flush()
        logger.info(
            "resume profile ready interview=%s name=%s skills=%s",
            interview.id,
            display_name or "?",
            profile.get("key_skills"),
        )
        return profile

    async def analyze_documents(self, db: AsyncSession, interview: Interview) -> list[dict]:
        jd = (interview.job_description_text or "").strip()
        if not jd:
            raise ValueError("Загрузите описание вакансии — языки извлекаются только из неё")
        proposed = await self.document_analysis.analyze_job_description(jd)
        for item in proposed:
            db.add(
                Competency(
                    interview_id=interview.id,
                    skill=item["skill"],
                    level=item["level"],
                    weight=int(item.get("weight", 10)),
                    source=item.get("source", "inferred"),
                    confirmed=False,
                )
            )
        if (interview.resume_text or "").strip():
            await self.ensure_resume_profile(db, interview)
        interview.status = InterviewStatus.DOCUMENTS_UPLOADED.value
        await self._sync_sql_dialect(interview)
        return proposed

    async def update_competencies(
        self, db: AsyncSession, interview: Interview, items: list[CompetencyItem]
    ) -> None:
        normalized = normalize_weights(
            [{"skill": c.skill, "level": c.level, "weight": c.weight, "source": c.source} for c in items]
        )
        await db.execute(
            Competency.__table__.delete().where(Competency.interview_id == interview.id)  # type: ignore[attr-defined]
        )
        for c in normalized:
            db.add(
                Competency(
                    interview_id=interview.id,
                    skill=c["skill"],
                    level=c["level"],
                    weight=c["weight"],
                    source=c["source"],
                    confirmed=True,
                )
            )
        interview.status = InterviewStatus.COMPETENCIES_CONFIRMED.value
        interview.editor_language = primary_editor_language(normalized)
        await self._sync_sql_dialect(interview)

    async def clone_for_candidate(
        self,
        db: AsyncSession,
        source: Interview,
        *,
        candidate_name: str | None = None,
        resume_text: str | None = None,
    ) -> Interview:
        """Новое интервью с той же вакансией/скиллами/форматом, другой кандидат."""
        await db.refresh(source, attribute_names=["competencies"])
        manual_name = (candidate_name or "").strip() or None
        if manual_name and len(manual_name) > 255:
            manual_name = manual_name[:255]
        candidate = Candidate(
            email=f"anonymous-{secrets.token_hex(8)}@interview.local",
            name=manual_name,
            resume_text=(resume_text or "").strip() or None,
        )
        db.add(candidate)
        await db.flush()

        src_settings = dict(source.ai_settings or {})
        cloned_settings = {
            k: src_settings[k]
            for k in ("live_coding_ai_assistant", "session_mode", "test_max_turns", "sql_dialect")
            if k in src_settings
        }

        interview = Interview(
            employer_id=source.employer_id,
            candidate_id=candidate.id,
            template_id=source.template_id,
            access_token=secrets.token_urlsafe(32),
            job_description_text=source.job_description_text,
            resume_text=(resume_text or "").strip() or None,
            feedback_emails=list(source.feedback_emails or []),
            format_selection_mode=source.format_selection_mode,
            allowed_formats=list(source.allowed_formats or []),
            selected_format=source.selected_format,
            duration_minutes=source.duration_minutes,
            editor_language=source.editor_language,
            ai_settings=cloned_settings,
            status=InterviewStatus.FORMAT_SELECTED.value
            if source.selected_format
            else InterviewStatus.COMPETENCIES_CONFIRMED.value,
        )
        db.add(interview)
        await db.flush()

        for c in list(source.competencies):
            db.add(
                Competency(
                    interview_id=interview.id,
                    skill=c.skill,
                    level=c.level,
                    weight=c.weight,
                    source=c.source or "confirmed",
                    confirmed=True,
                )
            )
        await db.flush()
        await db.refresh(interview, attribute_names=["competencies"])

        from app.services.candidate_name import resolve_candidate_name

        resolved = resolve_candidate_name(
            manual_name=manual_name,
            resume_text=interview.resume_text,
            resume_filename=None,
        )
        if resolved:
            result = await db.execute(select(Candidate).where(Candidate.id == candidate.id))
            cand = result.scalar_one_or_none()
            if cand:
                cand.name = resolved

        await self._sync_sql_dialect(interview)
        await db.flush()
        return interview

    async def mark_candidate_joined(self, interview: Interview) -> None:
        if interview.status in _ACTIVE_STATUSES:
            return
        if interview.status in (
            InterviewStatus.COMPLETED.value,
            InterviewStatus.REPORT_READY.value,
        ):
            return
        interview.status = InterviewStatus.CANDIDATE_JOINED.value

    async def ensure_briefing(self, db: AsyncSession, interview: Interview) -> tuple[str, str | None]:
        voice = self.voice.settings.effective_tts_voice
        text = briefing_text(voice)
        settings = dict(interview.ai_settings or {})
        message_id = settings.get("briefing_message_id") or f"briefing-{interview.id}"
        if not settings.get("briefing_message_id"):
            settings["briefing_message_id"] = message_id
            interview.ai_settings = settings
            await self.transcript_manager.add_entry(db, interview.id, "ai", text)

        audio_url = f"/api/v1/interviews/{interview.id}/tts-audio/{message_id}"
        cached = self.voice.tts_path(str(message_id))
        if cached.exists() and cached.stat().st_size > 0:
            return text, audio_url

        # Сохраняем транскрипт и отпускаем блокировку SQLite до долгого TTS.
        await db.commit()

        try:
            path = await asyncio.wait_for(
                self.voice.text_to_speech(text, str(message_id)),
                timeout=120.0,
            )
        except asyncio.TimeoutError:
            logger.warning("briefing TTS timeout interview=%s", interview.id)
            return text, None
        except Exception as exc:
            logger.warning("briefing TTS failed: %s", exc)
            return text, None

        if path and path.exists() and path.stat().st_size > 0:
            return text, audio_url
        return text, None

    async def ensure_warmup_quiz(self, db: AsyncSession, interview: Interview) -> list[dict]:
        """Банк коротких MCQ для ожидания STT/TTS — один раз при генерации ссылки."""
        competencies = [
            {"skill": c.skill, "level": c.level, "weight": c.weight}
            for c in interview.competencies
        ]
        if not competencies:
            return []

        existing = get_warmup_quiz(interview)
        if existing:
            kept = scrub_warmup_quiz_quality(interview)
            # старые LLM-банки часто «гнилые»: после scrub мало валидных — пересобираем из seed
            if kept >= 25:
                if warmup_needs_rebalance(interview):
                    rebalance_warmup_option_order(interview)
                await db.flush()
                return get_warmup_quiz_public(interview)
            logger.warning(
                "warmup quiz rebuild interview=%s kept_after_scrub=%s",
                interview.id,
                kept,
            )

        questions = await self._generate_warmup_bank(interview, competencies, WARMUP_QUIZ_INITIAL_COUNT)
        if not questions:
            return []
        set_warmup_quiz(interview, questions)
        await db.flush()
        logger.info("warmup quiz ready interview=%s count=%s", interview.id, len(questions))
        return get_warmup_quiz_public(interview)

    async def refill_warmup_quiz(
        self,
        db: AsyncSession,
        interview: Interview,
        batch_size: int = WARMUP_QUIZ_REFILL_BATCH,
    ) -> dict:
        """Догрузить новые MCQ, если банк исчерпан во время интервью."""
        competencies = [
            {"skill": c.skill, "level": c.level, "weight": c.weight}
            for c in interview.competencies
        ]
        if not competencies:
            return {"added": 0, "total": 0, "questions": []}
        before = len(get_warmup_quiz(interview))
        new_questions = await self._generate_warmup_bank(
            interview,
            competencies,
            batch_size,
            existing_hint=existing_questions_hint(interview),
        )
        added = append_warmup_questions(interview, new_questions)
        await db.flush()
        total = len(get_warmup_quiz(interview))
        logger.info(
            "warmup quiz refill interview=%s added=%s before=%s total=%s",
            interview.id,
            added,
            before,
            total,
        )
        return {
            "added": added,
            "total": total,
            "questions": get_warmup_quiz_public(interview),
        }

    async def _generate_warmup_bank(
        self,
        interview: Interview,
        competencies: list[dict],
        count: int,
        *,
        existing_hint: str = "",
    ) -> list[dict]:
        """Сначала проверенный seed-банк, LLM — только добор с quality gate."""
        from app.services.warmup_quiz import normalize_warmup_questions
        from app.services.warmup_quiz_seed import curated_warmup_questions

        seed = curated_warmup_questions(competencies, count=count)
        # Проверенный банк важнее объёма: LLM-ключи систематически ошибаются.
        if len(seed) >= min(25, count):
            if len(seed) >= count:
                return seed[:count]
            # добираем ещё раз из seed с новыми id (другие формулировки не выдумываем)
            extra = curated_warmup_questions(competencies, count=count)
            from app.services.warmup_quiz import _question_signature, _topic_signature

            seen = {_question_signature(q) for q in seed} | {_topic_signature(q) for q in seed}
            merged = list(seed)
            for item in extra:
                # одинаковые тексты — пропускаем; иначе seed уже уникален по теме
                sig = _question_signature(item)
                if sig in seen:
                    continue
                seen.add(sig)
                merged.append(item)
                if len(merged) >= count:
                    break
            logger.info(
                "warmup bank seed-only interview=%s total=%s",
                interview.id,
                len(merged),
            )
            return merged[:count]

        need = count - len(seed)
        ctx = InterviewContext(
            job_description=interview.job_description_text or "",
            resume=interview.resume_text or "",
            competencies=competencies,
            format_name=interview.selected_format or "Live Coding",
            sql_dialect=get_interview_sql_dialect(interview) or "",
        )
        llm_part: list[dict] = []
        try:
            hint = existing_hint or ""
            seed_hint = "Уже есть проверенные вопросы (не повторяй темы):\n" + "\n".join(
                f"- [{q.get('skill')}] {str(q.get('question', ''))[:100]}" for q in seed[:40]
            )
            llm_raw = await self.orchestrator.generate_warmup_quiz(
                ctx, count=need, existing_hint=(hint + "\n\n" + seed_hint).strip()
            )
            llm_part = normalize_warmup_questions(llm_raw, competencies)
        except Exception as exc:
            logger.warning("warmup quiz LLM fill failed interview=%s: %s", interview.id, exc)

        # дедуп seed + llm
        from app.services.warmup_quiz import _question_signature, _topic_signature

        seen = {_question_signature(q) for q in seed} | {_topic_signature(q) for q in seed}
        merged = list(seed)
        for item in llm_part:
            sig, topic = _question_signature(item), _topic_signature(item)
            if sig in seen or topic in seen:
                continue
            seen.add(sig)
            seen.add(topic)
            merged.append(item)
            if len(merged) >= count:
                break
        if len(merged) < max(8, count // 5):
            from app.services.warmup_quiz import mock_warmup_questions

            for item in mock_warmup_questions(competencies, count):
                sig, topic = _question_signature(item), _topic_signature(item)
                if sig in seen or topic in seen:
                    continue
                seen.add(sig)
                seen.add(topic)
                merged.append(item)
                if len(merged) >= count:
                    break
        logger.info(
            "warmup bank built interview=%s seed=%s llm=%s total=%s",
            interview.id,
            len(seed),
            len(merged) - len(seed),
            len(merged),
        )
        return merged[:count]

    async def submit_warmup_quiz_answer(
        self,
        db: AsyncSession,
        interview: Interview,
        question_id: str,
        selected_index: int,
        *,
        timed_out: bool = False,
    ) -> dict:
        if interview.status not in (InterviewStatus.ACTIVE.value, InterviewStatus.PAUSED.value):
            raise ValueError("Интервью не активно")
        entry = record_warmup_quiz_answer(
            interview,
            question_id=question_id,
            selected_index=selected_index,
            timed_out=timed_out,
        )
        await db.flush()
        return {
            "recorded": True,
            "is_correct": entry.get("is_correct"),
            "timed_out": entry.get("timed_out"),
            "correct_index": entry.get("correct_index"),
            "excluded_from_score": entry.get("excluded_from_score", False),
        }

    async def skip_warmup_quiz_question(
        self,
        db: AsyncSession,
        interview: Interview,
        question_id: str,
        *,
        reason: str = "submit_failed",
    ) -> dict:
        if interview.status not in (InterviewStatus.ACTIVE.value, InterviewStatus.PAUSED.value):
            raise ValueError("Интервью не активно")
        entry = record_warmup_quiz_skip(
            interview,
            question_id=question_id,
            reason=reason,
        )
        await db.flush()
        return {
            "recorded": False,
            "skipped": True,
            "excluded_from_score": True,
            "correct_index": entry.get("correct_index", 0),
        }

    async def select_format(self, db: AsyncSession, interview: Interview) -> str:
        ctx = await self._build_context(db, interview)
        allowed = normalize_format_list(interview.allowed_formats or [])
        if interview.format_selection_mode == "manual" and interview.selected_format:
            fmt = interview.selected_format
        elif len(allowed) >= 2:
            fmt = " + ".join(allowed)
        elif len(allowed) == 1:
            fmt = allowed[0]
        else:
            result = await self.orchestrator.select_interview_format(ctx, allowed)
            fmt = result.get("format", "Live Coding")
        interview.selected_format = fmt
        interview.status = InterviewStatus.FORMAT_SELECTED.value
        return fmt

    async def generate_link(self, interview: Interview, base_url: str | None = None) -> str:
        interview.status = InterviewStatus.SESSION_LINK_GENERATED.value
        from app.config import fresh_settings

        root = (base_url or fresh_settings().frontend_public_url).rstrip("/")
        return f"{root}/interview/{interview.access_token}"

    def media_ready(self, interview: Interview) -> bool:
        return interview.media_camera and interview.media_microphone and interview.media_screenshare

    async def update_media(self, db: AsyncSession, interview: Interview, camera: bool, mic: bool, screen: bool) -> None:
        interview.media_camera = camera
        interview.media_microphone = mic
        interview.media_screenshare = screen
        if self.media_ready(interview):
            if interview.status == InterviewStatus.PAUSED.value and interview.started_at:
                interview.status = InterviewStatus.ACTIVE.value
            elif interview.status in (
                InterviewStatus.CANDIDATE_JOINED.value,
                InterviewStatus.MEDIA_PRECHECK.value,
                InterviewStatus.SESSION_LINK_GENERATED.value,
            ):
                interview.status = InterviewStatus.READY.value
        # Во время активного интервью таймер не останавливаем — только фиксируем состояние медиа.

    async def start_interview(self, db: AsyncSession, interview: Interview) -> None:
        if not self.media_ready(interview):
            raise ValueError("Media requirements not met")
        if interview.status == InterviewStatus.ACTIVE.value and interview.started_at:
            return
        interview.status = InterviewStatus.ACTIVE.value
        if not interview.started_at:
            interview.started_at = datetime.now(timezone.utc)

    async def process_candidate_answer(
        self,
        db: AsyncSession,
        interview: Interview,
        answer_text: str,
        answer_type: str,
    ) -> dict:
        if interview.status not in (InterviewStatus.ACTIVE.value, InterviewStatus.PAUSED.value):
            raise ValueError("Interview is not active")

        if answer_text.strip() == "[Interview started]":
            await runtime_debug_trace(db, interview, "opening_path_start")
            voice = self.voice.settings.effective_tts_voice
            briefing = briefing_text(voice)
            history = await self.transcript_manager.get_history(db, interview.id)
            prior = [
                h
                for h in history
                if h.get("speaker") == "ai" and briefing not in (h.get("text") or "")
            ]
            opening_id = f"opening-{interview.id}"
            if prior:
                last_ai = prior[-1].get("text", "")
                return {"message": last_ai, "code_actions": [], "message_id": opening_id}

            # Не вызываем LLM анализа резюме во время старта — он блокирует мини-тест на минуты.
            profile = filter_resume_profile_for_competencies(
                get_resume_profile(interview),
                [{"skill": c.skill} for c in interview.competencies],
            )
            if profile and not str(profile.get("opening_question") or "").strip():
                profile = None
            skills = [c.skill for c in interview.competencies]
            opening = opening_turn_text(voice, skills, resume_profile=profile)
            await self.transcript_manager.add_entry(db, interview.id, "candidate", answer_text)
            opening_tx = ai_transcript_with_editor_code(
                opening,
                interview.editor_content,
                format_name=interview.selected_format or "",
                code_actions=[],
            )
            await self.transcript_manager.add_entry(db, interview.id, "ai", opening_tx)
            await runtime_debug_trace(
                db,
                interview,
                "opening_path_done",
                message_chars=len(opening),
                message_id=opening_id,
            )
            return {"message": opening, "code_actions": [], "message_id": opening_id}

        payload = answer_text.strip()
        code_body = (interview.editor_content or "").strip()
        if answer_type in ("combined", "code") and code_body:
            if payload:
                payload = f"{payload}\n\n[Код в редакторе]\n{code_body}"
            else:
                payload = f"[Ответ в редакторе]\n{code_body}"
        if not payload:
            raise ValueError("Пустой ответ: скажите ответ вслух и/или введите код")

        baseline = get_exercise_baseline(interview)
        change_notice = build_code_change_notice(baseline, code_body)
        if change_notice and answer_type in ("combined", "code"):
            payload = f"{payload}\n\n[Статус правок кода]\n{change_notice}"

        await self.transcript_manager.add_entry(db, interview.id, "candidate", payload)

        settings = get_settings()
        prog = get_progress(interview.ai_settings)
        from app.services.interview_formats import interview_is_test_mode, interview_test_max_turns

        if interview_is_test_mode(interview):
            max_t = interview_test_max_turns(interview)
            if prog.get("ai_turn_count", 0) + 1 >= max_t:
                bump_after_answer(
                    interview,
                    payload,
                    substantive=candidate_answer_is_substantive(answer_text),
                )
                farewell = (
                    "Спасибо за ответы! Тестовый прогон завершён — сейчас сформируем отчёт."
                )
                mid = str(uuid.uuid4())
                await self.transcript_manager.add_entry(db, interview.id, "ai", farewell)
                return {
                    "message": farewell,
                    "code_actions": [],
                    "end_interview": True,
                    "message_id": mid,
                }

        ctx = await self._build_context(db, interview)
        ctx.exercise_baseline_code = baseline
        ctx.code_change_notice = change_notice
        ctx.dialog_directives = build_dialog_directives(
            ctx.transcript_history,
            payload,
            remaining_minutes=ctx.remaining_minutes,
        )
        if answer_type in ("voice", "combined") and answer_text.strip():
            ctx.stt_quality_note = STT_QUALITY_NOTE

        settings = get_settings()
        prog = get_progress(interview.ai_settings)
        if not prog.get("difficulty_seeded"):
            prog["current_difficulty"] = difficulty_for_levels(ctx.competencies)
            prog["difficulty_seeded"] = True
            save_progress(interview, prog)
        ctx.current_difficulty = prog.get("current_difficulty", "medium")
        ctx.asked_questions_block = asked_questions_block(interview.ai_settings)
        preferred = preferred_competency(
            interview,
            ctx.competencies,
            remaining_minutes=ctx.remaining_minutes,
            duration_minutes=interview.duration_minutes or 60,
        )
        ctx.preferred_competency = preferred
        ctx.skill_plan_block = skill_plan_prompt_block(
            preferred, ctx.competencies, ctx.remaining_minutes
        )
        if interview_is_test_mode(interview):
            ctx.test_mode = True
            max_t = interview_test_max_turns(interview)
            ctx.test_turns_left = max(0, max_t - prog.get("ai_turn_count", 0))

        bump_after_answer(
            interview,
            payload,
            substantive=candidate_answer_is_substantive(answer_text),
        )
        # Критично для SQLite: не держать write-lock на время LLM (иначе чанки записи
        # и мини-тест ловят «database is locked», а UI зависает на доп. тесте).
        await db.commit()
        await db.refresh(interview)

        try:
            turn = await self.orchestrator.next_interview_turn(ctx, payload, answer_type)
        except Exception:
            skill = preferred or (
                ctx.competencies[0].get("skill", "Python") if ctx.competencies else "Python"
            )
            turn = {
                "message": (
                    f"Следующая задача по {skill}: внесите в редактор решение "
                    "и кратко поясните ключевую идею."
                ),
                "code_actions": [],
                "competency_focus": skill,
                "end_interview": False,
            }
        if is_generic_ai_message(turn.get("message", "")):
            turn["message"] = (
                "Новый вопрос: что измените в вашем запросе, если нужно учесть пустые значения "
                "в данных? Ответьте устно или правкой в редакторе."
            )
        turn = normalize_ai_turn(turn)
        turn = apply_dialog_policy_to_turn(
            turn,
            transcript_history=ctx.transcript_history,
            candidate_answer=payload,
            language=ctx.language,
            remaining_minutes=ctx.remaining_minutes,
            competencies=ctx.competencies,
        )
        # Применить difficulty от LLM, если выше текущей
        llm_diff = str(turn.get("difficulty") or "").lower().strip()
        if llm_diff in _DIFFICULTY_RANK:
            cur = str(get_progress(interview.ai_settings).get("current_difficulty") or "easy")
            if _DIFFICULTY_RANK[llm_diff] >= _DIFFICULTY_RANK.get(cur, 0):
                p = get_progress(interview.ai_settings)
                p["current_difficulty"] = llm_diff
                save_progress(interview, p)

        focus = turn.get("competency_focus") or preferred
        turn["competency_focus"] = focus
        record_skill_coverage(interview, focus, list(interview.competencies or []))

        ai_text = turn.get("message", "")
        register_ai_question(interview, ai_text)
        turn["message_id"] = turn.get("message_id") or str(uuid.uuid4())
        return turn

    async def complete_interview(self, db: AsyncSession, interview: Interview) -> None:
        interview.status = InterviewStatus.COMPLETING.value
        interview.ended_at = datetime.now(timezone.utc)
        ctx = await self._build_context(db, interview)
        await self.report_builder.build_and_persist(db, interview.id, ctx)
        interview.status = InterviewStatus.REPORT_READY.value

    async def _build_context(self, db: AsyncSession, interview: Interview) -> InterviewContext:
        history = await self.transcript_manager.get_history(db, interview.id)
        competencies = [
            {"skill": c.skill, "level": c.level, "weight": c.weight, "coverage": c.coverage_score}
            for c in interview.competencies
        ]
        remaining = interview.duration_minutes
        started = ensure_utc(interview.started_at)
        if started:
            elapsed = (datetime.now(timezone.utc) - started).total_seconds() / 60
            remaining = max(0, int(interview.duration_minutes - elapsed))
        profile = filter_resume_profile_for_competencies(
            get_resume_profile(interview) or {},
            competencies,
        )
        candidate_name = (profile.get("candidate_first_name") or "").strip()
        if not candidate_name and interview.candidate and interview.candidate.name:
            candidate_name = interview.candidate.name.strip()

        fmt = interview.selected_format or "Live Coding"
        if LEGACY_AI_ASSISTED_FORMAT in fmt and LEGACY_AI_ASSISTED_FORMAT not in (interview.allowed_formats or []):
            fmt = "Live Coding"

        return InterviewContext(
            job_description=interview.job_description_text or "",
            resume=interview.resume_text or "",
            resume_profile=profile,
            candidate_first_name=candidate_name,
            competencies=competencies,
            format_name=fmt,
            live_coding_ai_assistant=get_live_coding_ai_assistant(interview),
            mode_settings=interview.ai_settings or {},
            current_code=interview.editor_content,
            language=interview.editor_language,
            transcript_history=history,
            coverage={c.skill: c.coverage_score for c in interview.competencies},
            remaining_minutes=remaining,
            warmup_quiz_summary=warmup_quiz_summary_for_prompt(interview),
            sql_dialect=get_interview_sql_dialect(interview) or "",
        )
