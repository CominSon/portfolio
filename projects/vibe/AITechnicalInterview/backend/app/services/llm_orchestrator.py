"""Оркестрация LLM: компетенции, формат, ход интервью, отчёт. Mock без API-ключа."""
import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.config import get_settings
from app.services.interview_formats import ALL_FORMATS, format_guidance_block
from app.services.interview_progress import is_generic_ai_message
from app.services.llm_client import LlmClient
from app.services.report_postprocess import agent_issues_from_transcript, sanitize_report_data
from app.services.interview_skills import skills_only_prompt_rule
from app.services.resume_analyzer import profile_summary_for_prompt
from app.services.sql_dialect import sql_dialect_prompt_hint
from app.services.tts_prepare import is_female_voice

logger = logging.getLogger(__name__)


@dataclass
class InterviewContext:
    """Снимок состояния интервью для промпта LLM."""
    job_description: str = ""
    resume: str = ""
    resume_profile: dict = field(default_factory=dict)
    candidate_first_name: str = ""
    competencies: list[dict] = field(default_factory=list)
    format_name: str = "Live Coding"
    mode_settings: dict = field(default_factory=dict)
    current_code: str = ""
    exercise_baseline_code: str = ""
    code_change_notice: str = ""
    dialog_directives: str = ""
    stt_quality_note: str = ""
    language: str = "python"
    transcript_history: list[dict] = field(default_factory=list)
    coverage: dict[str, float] = field(default_factory=dict)
    remaining_minutes: int = 60
    current_difficulty: str = "easy"
    asked_questions_block: str = ""
    preferred_competency: str = ""
    skill_plan_block: str = ""
    live_coding_ai_assistant: bool = False
    test_mode: bool = False
    test_turns_left: int = 0
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    warmup_quiz_summary: str = ""
    sql_dialect: str = "PostgreSQL"


class LlmOrchestrator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = LlmClient()

    async def _chat(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        if self.settings.mock_ai or not self.llm.api_key:
            return self._mock_response(messages)
        try:
            return await self.llm.chat_completion(messages, temperature=temperature)
        except Exception as exc:
            logger.error("LLM unavailable, using fallback: %s", exc)
            return self._mock_response(messages)

    def _mock_response(self, messages: list[dict[str, str]]) -> str:
        last = messages[-1]["content"] if messages else ""
        if "competenc" in last.lower() or "компетенц" in last.lower() or "язык" in last.lower():
            return json.dumps(
                [
                    {"skill": "Python", "level": "Senior", "weight": 40, "source": "inferred"},
                    {"skill": "SQL", "level": "Middle", "weight": 35, "source": "inferred"},
                    {"skill": "Go", "level": "Middle", "weight": 25, "source": "inferred"},
                ],
                ensure_ascii=False,
            )
        if "format" in last.lower() or "формат" in last.lower():
            return json.dumps({"format": "Live Coding", "reason": "Strong Python backend profile"}, ensure_ascii=False)
        if "warmup" in last.lower() or "mcq" in last.lower() or "коротк" in last.lower():
            from app.services.warmup_quiz import mock_warmup_questions

            return json.dumps(mock_warmup_questions([{"skill": "Python"}, {"skill": "SQL"}], 12), ensure_ascii=False)
        if (
            "sql dialect" in last.lower()
            or "диалект sql" in last.lower()
            or "sql-диалект" in last.lower()
            or "определи sql" in last.lower()
        ):
            from app.services.sql_dialect import ALLOWED_SQL_DIALECTS, resolve_sql_dialect

            jd_excerpt = ""
            resume_excerpt = ""
            for marker, var in (("Вакансия:", "jd_excerpt"), ("Резюме:", "resume_excerpt")):
                if marker in last:
                    chunk = last.split(marker, 1)[1].split("\n\n", 1)[0]
                    if var == "jd_excerpt":
                        jd_excerpt = chunk
                    else:
                        resume_excerpt = chunk
            dialect = resolve_sql_dialect(jd_excerpt, resume_excerpt) or "ANSI SQL"
            if dialect not in ALLOWED_SQL_DIALECTS:
                dialect = "ANSI SQL"
            return json.dumps(
                {"dialect": dialect, "reason": "mock: эвристика по тексту вакансии и резюме"},
                ensure_ascii=False,
            )
        if "report" in last.lower() or "отчёт" in last.lower():
            return json.dumps(
                {
                    "competency_scores": {"Python": 78, "SQL": 65},
                    "strengths": [
                        "Понятно объясняет решения",
                        "Уверенно пишет код на Python",
                    ],
                    "weaknesses": ["Слабо раскрыл обработку ошибок"],
                    "communication_assessment": {
                        "ясность": "хорошая",
                        "глубина": "средняя",
                        "итог": "Достаточно для middle+",
                    },
                    "code_quality_assessment": {
                        "структура": "хорошая",
                        "именование": "приемлемое",
                    },
                    "honesty_signals": {"признание незнания": "честно"},
                    "confidence_level": 0.75,
                    "recommendation": "good_fit",
                    "final_summary": (
                        "Кандидат демонстрирует уверенный уровень Python для позиции middle+. "
                        "Рекомендуется на техническое интервью с командой."
                    ),
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "message": "Расскажите, как бы вы спроектировали API для высоконагруженного сервиса?",
                "code_actions": [],
                "competency_focus": "Python",
                "difficulty": "medium",
                "end_interview": False,
            },
            ensure_ascii=False,
        )

    async def infer_competencies_from_job_description(self, job_description: str) -> list[dict]:
        allowed = (
            "Python, SQL, Java, JavaScript, TypeScript, Go, C++, C#, Rust, Kotlin, Swift, "
            "PHP, Ruby, Scala, R, Dart, Lua, Perl, Objective-C, Haskell, Elixir"
        )
        prompt = f"""Проанализируй ТОЛЬКО текст вакансии ниже.
Извлеки языки программирования и SQL (если явно указан в вакансии), требуемые для позиции.
НЕ используй резюме кандидата (его нет).
НЕ включай: Docker, Kubernetes, Git, Agile, soft skills, фреймворки как отдельные навыки.
Максимум 6 позиций. Сумма weight = 100.

Допустимые названия (канонические): {allowed}

Верни ТОЛЬКО JSON-массив:
[{{"skill": str, "level": "Junior"|"Middle"|"Senior", "weight": int, "source": "inferred"}}]

Вакансия:
{job_description[:12000] or "(пусто)"}"""
        raw = await self._chat(
            [
                {
                    "role": "system",
                    "content": "Ты эксперт по техническим вакансиям. Отвечай только валидным JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return self._parse_json(raw, default=[])

    async def infer_sql_dialect(
        self,
        job_description: str,
        resume_text: str = "",
        *,
        supplemental_skills: list[str] | None = None,
    ) -> str | None:
        from app.services.sql_dialect import ALLOWED_SQL_DIALECTS, normalize_sql_dialect_name

        allowed = ", ".join(ALLOWED_SQL_DIALECTS)
        skills_line = ""
        if supplemental_skills:
            skills_line = (
                f"\nКомпетенции для проверки на интервью (в т.ч. выбранные вручную): "
                f"{', '.join(supplemental_skills[:12])}"
            )
        prompt = f"""Определи SQL-диалект для технического интервью.

Правила:
1. Сначала смотри вакансию — если диалект указан явно (Greenplum, PostgreSQL, ClickHouse, MySQL, …), выбери его.
2. Если в вакансии только «SQL» / «базы данных» без диалекта — ОБЯЗАТЕЛЬНО ищи диалект в резюме (стек, опыт, технологии: PostgreSQL, Postgres, постгрес, MySQL, Oracle и т.д.).
3. Конкретный диалект из резюме важнее общей формулировки «SQL» в вакансии. Не возвращай «ANSI SQL», если в резюме или навыках есть PostgreSQL/MySQL/Greenplum/…
4. «ANSI SQL» — только если ни в вакансии, ни в резюме, ни в навыках нет ни одного конкретного диалекта.
5. Если SQL есть в списке компетенций — он релевантен, даже если в вакансии не назван.
6. Верни dialect: null только если SQL нигде не фигурирует и не планируется к проверке.

Допустимые значения dialect (строго из списка): {allowed}

Верни ТОЛЬКО JSON:
{{"dialect": str|null, "reason": str}}

Вакансия:
{job_description[:8000] or "(пусто)"}

Резюме:
{resume_text[:8000] or "(пусто)"}{skills_line}"""
        raw = await self._chat(
            [
                {
                    "role": "system",
                    "content": "Ты эксперт по SQL и техническим вакансиям. Отвечай только валидным JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        parsed = self._parse_json(raw, default={})
        if not isinstance(parsed, dict):
            return None
        dialect = normalize_sql_dialect_name(parsed.get("dialect"))
        if dialect:
            return dialect
        return None

    async def select_interview_format(
        self, ctx: InterviewContext, allowed_formats: list[str]
    ) -> dict[str, str]:
        allowed = allowed_formats or ALL_FORMATS
        if len(allowed) >= 2:
            combined = " + ".join(allowed)
            return {
                "format": combined,
                "reason": "Работодатель разрешил несколько форматов — комбинируйте их в одной сессии.",
            }
        prompt = f"""Select best interview format from: {allowed}.
Return JSON: {{"format": str, "reason": str}}
Competencies: {json.dumps(ctx.competencies, ensure_ascii=False)}
JD excerpt: {ctx.job_description[:2000]}
Resume excerpt: {ctx.resume[:2000]}"""
        raw = await self._chat(
            [
                {"role": "system", "content": "Output valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return self._parse_json(raw, default={"format": allowed[0], "reason": "default"})

    async def next_interview_turn(
        self, ctx: InterviewContext, candidate_answer: str, answer_type: str
    ) -> dict[str, Any]:
        voice = self.settings.effective_tts_voice
        gender_rule = (
            "Use feminine grammar for yourself (я готова, я задала, я услышала)."
            if is_female_voice(voice)
            else "Use masculine grammar for yourself (я готов, я задал, я услышал)."
        )
        name_rule = ""
        if ctx.candidate_first_name.strip():
            name_rule = (
                f"- Address the candidate by first name «{ctx.candidate_first_name.strip()}» "
                f"regularly (not in every sentence). Never invent another name.\n"
            )
        profile_block = profile_summary_for_prompt(
            ctx.resume_profile, allowed_skills=[c.get("skill", "") for c in ctx.competencies]
        )
        resume_ctx = ""
        if profile_block:
            resume_ctx = (
                "- Resume profile (internal context only — NEVER read aloud, never repeat PII):\n"
                f"{profile_block}\n"
            )
        skills_rule = skills_only_prompt_rule(ctx.competencies)
        dialect_rule = sql_dialect_prompt_hint(ctx.sql_dialect) if ctx.sql_dialect else ""
        dialect_block = f"\n{dialect_rule}\n" if dialect_rule else ""
        system = f"""You are an AI technical interviewer (Айри). Rules:
- Never interrupt; respond only after candidate submits.
- {gender_rule}
{name_rule}{skills_rule}{dialect_block}{resume_ctx}- Speak naturally in Russian with short clear sentences.
- Adapt difficulty: strong answers → harder; weak → simpler.
- Time is limited: cover different competencies and aspects; do NOT drill one subtopic repeatedly.
- Do NOT execute code; analyze statically only.
- CRITICAL: Any source code for the candidate MUST go in code_actions, NEVER inside "message".
- "message" is only what you say aloud (Russian prose). No markdown code fences, no multi-line code in message.
- When you ask to review or fix code, put the full snippet in code_actions with action "replace" ONLY for a NEW exercise.
- NEW exercise / new language / new task: ALWAYS send code_actions with action "replace" (full starter snippet). Never ask to look at the editor without providing that snippet.
- Follow-up on the SAME exercise (clarify edge case, ask about their edits): set continue_exercise=true and leave code_actions empty — do NOT replace their code.
- After the candidate edits code in the editor, evaluate THEIR version from [Код в редакторе] and Code block below.
- If [Статус правок кода] says the code WAS changed, you MUST acknowledge their edits. NEVER say "вы не изменили код".
- NEVER use code_actions replace to restore an older snippet after the candidate submitted fixes.
- When switching competency (e.g. SQL → Python), always start a NEW exercise with replace snippet; never leave previous-language code in the editor.
- Follow the interview format guidance below (may combine several modes with «+»).
- When competency_focus is SQL, use the vacancy SQL dialect from context below.
- For EVERY new SQL exercise in code_actions: include short CREATE TABLE (or commented schema) PLUS 3–6 rows of sample INSERT/data as comments or VALUES, so the candidate sees concrete table contents — never ask to rewrite SQL without showing the task code and sample data.
- When competency_focus is Python, assume Python.
- STT: candidate voice is auto-transcribed; text may have errors or missing fragments — infer intent generously, do not penalize odd wording.
- If [STT quality note] is present, treat transcript as approximate.

DIALOG (critical):
- FORBIDDEN generic phrases: «подробнее объясните решение», «раскройте мысль», «можете подробнее» without naming a SPECIFIC gap (line, NULL, index, edge case).
- If the candidate gave a substantive answer (several sentences, reasoning, approach): briefly acknowledge (1 phrase) and ask ONE new concrete question on a DIFFERENT aspect, or move to the next task.
- Max ONE follow-up on the same subtopic; then switch topic or task.
- If the candidate says «давай дальше», «пропустим», «уже объяснил» — immediately change topic/task; do not insist on explanation.
- If they cannot explain — give a short hint OR move on; never repeat the same question verbatim.
- When little time remains (Remaining minutes low), prioritize breadth over depth.
- Current difficulty: {ctx.current_difficulty}. Match tasks to the vacancy level for competency_focus (Senior → hard: windows, concurrency, edge cases — NOT trivial alias-in-WHERE bugs).
- NEVER repeat questions from the "already asked" list — new task or new aspect only.
- Vary openings: do NOT default to is_palindrome or «second highest order» every interview.
{ctx.skill_plan_block}
- FORBIDDEN empty replies like "перейдём к следующему аспекту" without a NEW concrete question or code task in the same message.
- If test_mode: you have {ctx.test_turns_left} candidate answer(s) left before auto-close — be concise.
- Priority for topic selection: ONLY competencies listed below; resume is secondary context, not a reason to ask off-list skills.

Return JSON:
{{
  "message": "spoken text in Russian only (no code blocks)",
  "code_actions": [
    {{"action": "replace"|"insert"|"delete", "range": {{"startLine": 1, "startColumn": 1, "endLine": 9999, "endColumn": 1}}, "text": "code here"}}
  ],
  "continue_exercise": false,
  "competency_focus": str,
  "difficulty": "easy|medium|hard",
  "end_interview": false
}}
Set continue_exercise true only when the candidate should keep working on the same editor code (follow-up). For a new task set continue_exercise false and provide code_actions replace.
Set end_interview true only when you intentionally close the session (no more questions, thank candidate, suggest pressing Finish)."""
        baseline_block = ""
        if ctx.exercise_baseline_code.strip():
            baseline_block = f"""
Exercise baseline (code AI gave for this task):
```
{ctx.exercise_baseline_code[:12000]}
```
"""
        notice_block = ""
        if ctx.code_change_notice.strip():
            notice_block = f"\nCode edit status: {ctx.code_change_notice}\n"

        dialog_block = ""
        if ctx.dialog_directives.strip():
            dialog_block = f"\nDialog policy:\n{ctx.dialog_directives}\n"

        format_block = format_guidance_block(
            ctx.format_name, live_coding_ai_assistant=ctx.live_coding_ai_assistant
        )
        ai_assist_block = ""
        if ctx.live_coding_ai_assistant:
            ai_assist_block = (
                "\nРежим AI-помощника в редакторе: задавай крупные задачи (несколько классов/модулей), "
                "оценивай мышление, качество промптов и итоговый код с комментариями.\n"
            )
        stt_block = ""
        if ctx.stt_quality_note.strip():
            stt_block = f"\n[STT quality note]\n{ctx.stt_quality_note.strip()}\n"

        user = f"""Format: {ctx.format_name}
{format_block}{ai_assist_block}
{sql_dialect_prompt_hint(ctx.sql_dialect) if ctx.sql_dialect else ""}
Remaining minutes: {ctx.remaining_minutes}
Preferred competency now: {ctx.preferred_competency or "(any from list)"}
Competencies: {json.dumps(ctx.competencies, ensure_ascii=False)}
Coverage (0=не проверяли, 1=хорошо покрыто): {json.dumps(ctx.coverage, ensure_ascii=False)}
{ctx.asked_questions_block}{baseline_block}{notice_block}{stt_block}{dialog_block}Current editor code ({ctx.language}):
```
{ctx.current_code[:12000]}
```
Recent transcript: {json.dumps(ctx.transcript_history[-10:], ensure_ascii=False)}
Candidate {answer_type} answer: {candidate_answer}"""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        raw = await self._chat(messages, temperature=0.6)
        turn = self._parse_json(raw, default=None)
        if not turn or is_generic_ai_message(str(turn.get("message", ""))):
            logger.warning("LLM turn generic or invalid JSON — retry")
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Ответ должен содержать НОВЫЙ конкретный вопрос или новую задачу в code_actions. "
                        "Не используй шаблон «перейдём к следующему аспекту» без содержания."
                    ),
                }
            )
            raw = await self._chat(messages, temperature=0.65)
            turn = self._parse_json(raw, default=None)
        if not turn:
            skill = ctx.competencies[0].get("skill", "") if ctx.competencies else "Python"
            fmt = ctx.format_name or ""
            if "Code Review" in fmt:
                dialect_note = f" (диалект {ctx.sql_dialect})" if ctx.sql_dialect and "sql" in skill.lower() else ""
                fallback_msg = (
                    f"Диалект: {ctx.sql_dialect}. " if ctx.sql_dialect and "sql" in skill.lower() else ""
                ) + (
                    f"Разберём код в редакторе по {skill}{dialect_note}: "
                    "найдите ошибки, риски с NULL и производительность. "
                    "Предложите правки устно или в редакторе."
                )
                sample_code = (
                    "-- Sample:\n"
                    "-- user_id | amount\n"
                    "-- 1       | 100\n"
                    "-- 1       | 50\n"
                    "-- 2       | NULL\n"
                    "CREATE TABLE transactions (\n"
                    "    customer_id INT,\n"
                    "    amount NUMERIC\n"
                    ");\n"
                    "INSERT INTO transactions VALUES (1, 100), (1, 50), (2, NULL);\n\n"
                    "SELECT customer_id, SUM(amount) AS total\n"
                    "FROM transactions\n"
                    "GROUP BY customer_id;"
                    if "sql" in skill.lower()
                    else "def process(items):\n    return sum(items) / len(items)"
                )
                turn = {
                    "message": fallback_msg,
                    "code_actions": [
                        {
                            "action": "replace",
                            "range": {
                                "startLine": 1,
                                "startColumn": 1,
                                "endLine": 9999,
                                "endColumn": 1,
                            },
                            "text": sample_code,
                        }
                    ],
                    "competency_focus": skill,
                    "difficulty": ctx.current_difficulty,
                    "end_interview": False,
                }
            elif ctx.live_coding_ai_assistant and "Live Coding" in fmt:
                fallback_msg = (
                    f"Задача по {skill} с AI-помощником в редакторе: спроектируйте модуль из 2–3 классов "
                    "для сервиса обработки заказов (создание, статусы, отмена). "
                    "Используйте помощника для черновика, но доработайте архитектуру и добавьте комментарии "
                    "к ключевым решениям. Поясните устно, какие промпты задавали и что проверили."
                )
            elif "Live Coding" in fmt:
                fallback_msg = (
                    f"Давайте сделаем короткую live coding задачу по {skill}: "
                    "реализуйте функцию, которая получает список чисел и возвращает словарь "
                    "с минимальным, максимальным и средним значением, с обработкой пустого списка. "
                    "После кода коротко объясните устно, как обработали edge cases."
                )
            else:
                fallback_msg = (
                    f"Новый вопрос по {skill}: расскажите конкретный кейс из практики, "
                    "где вы решали нетривиальную техническую проблему, и почему выбрали именно такой подход."
                )
            turn = {
                "message": fallback_msg,
                "code_actions": [],
                "competency_focus": skill,
                "difficulty": ctx.current_difficulty,
                "end_interview": False,
            }
        if ctx.test_mode and ctx.test_turns_left <= 0:
            turn["end_interview"] = True
            turn["message"] = (
                "Спасибо за ответы! Тестовый прогон завершён — сейчас сформируем отчёт."
            )
            turn["code_actions"] = []
        turn.setdefault("end_interview", False)
        turn.setdefault("difficulty", ctx.current_difficulty)
        return turn

    async def generate_warmup_quiz(
        self,
        ctx: InterviewContext,
        count: int = 100,
        *,
        existing_hint: str = "",
        batch_size: int | None = None,
    ) -> list[dict[str, Any]]:
        from app.services.warmup_quiz import (
            WARMUP_QUIZ_LLM_BATCH_SIZE,
            mock_warmup_questions,
            normalize_warmup_questions,
        )

        batch_size = batch_size or WARMUP_QUIZ_LLM_BATCH_SIZE
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()

        while len(merged) < count:
            need = min(batch_size, count - len(merged))
            batch = await self._generate_warmup_quiz_batch(
                ctx, need, existing_hint=existing_hint, batch_index=len(merged)
            )
            if not batch:
                break
            added_in_batch = 0
            for item in batch:
                from app.services.warmup_quiz import _question_signature, _topic_signature

                sig = _question_signature(item)
                topic = _topic_signature(item)
                if not sig or sig in seen or topic in seen:
                    continue
                seen.add(sig)
                seen.add(topic)
                merged.append(item)
                added_in_batch += 1
            if added_in_batch == 0:
                break

        if len(merged) < max(4, count // 2):
            for item in mock_warmup_questions(ctx.competencies, count):
                from app.services.warmup_quiz import _question_signature, _topic_signature

                sig = _question_signature(item)
                topic = _topic_signature(item)
                if sig and sig not in seen and topic not in seen:
                    seen.add(sig)
                    seen.add(topic)
                    merged.append(item)
                if len(merged) >= count:
                    break

        return merged[:count]

    async def _generate_warmup_quiz_batch(
        self,
        ctx: InterviewContext,
        count: int,
        *,
        existing_hint: str = "",
        batch_index: int = 0,
    ) -> list[dict[str, Any]]:
        from app.services.warmup_quiz import mock_warmup_questions, normalize_warmup_questions

        skills = [c.get("skill", "") for c in ctx.competencies if c.get("skill")]
        if not skills:
            skills = ["General"]
        hint_block = f"\n\n{existing_hint}" if existing_hint else ""
        prompt = f"""Подготовь ровно {count} коротких технических вопросов с вариантами ответа (MCQ).
Вопросы показываются во время ожидания (без озвучки), по одному, ~40 секунд на ответ.
Один правильный вариант, без множественного выбора.
Партия #{batch_index // max(count, 1) + 1} — id вопросов начинай с wq-{batch_index + 1}.

Навыки интервью (распредели вопросы по ним): {json.dumps(skills, ensure_ascii=False)}
Формат интервью: {ctx.format_name}
{sql_dialect_prompt_hint(ctx.sql_dialect) if ctx.sql_dialect else ""}
JD (фрагмент): {(ctx.job_description or '')[:2500]}
{hint_block}

Верни ТОЛЬКО JSON-массив:
[
  {{
    "id": "wq-1",
    "skill": "Python",
    "question": "Короткий понятный вопрос на русском",
    "options": ["вариант A", "вариант B", "вариант C", "вариант D"],
    "correct_index": 0
  }}
]

Правила:
- Все тексты на русском.
- Вопросы простые, но по делу (базовые концепции навыка).
- Ровно 4 варианта ответа, correct_index 0..3 (распределяй правильные ответы по разным позициям, не ставь всегда 0).
- Все 4 варианта должны быть РАЗНЫМИ по смыслу и формулировке (без дубликатов и опечаток вроде лишнего пробела в 'abc ').
- Фактическая точность ОБЯЗАТЕЛЬНА. Примеры:
  • 'ABC'.lower() → верный ответ "'abc'" (не «ошибка»).
  • range(5) → «объект range» / последовательность 0..4, НЕ «итератор» и НЕ list([...]).
  • список→кортеж → tuple(), не list().
  • LEFT JOIN — все строки левой таблицы + совпадения справа; не путать с FULL/INNER.
  • пробелы в начале строки → LTRIM(), не TRIM().
- Не делай смысловых дублей (например «2**3» и «print(2**3)» — это один и тот же вопрос).
- Для SQL в вопросе укажи диалект из вакансии в тексте вопроса (например: «Диалект: Greenplum»).
- Не повторяй формулировки из списка «Уже есть вопросы».
- Без PII, без ссылок на резюме."""
        raw = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты составляешь банк коротких MCQ для технического интервью. "
                        "Отвечай только валидным JSON-массивом."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )
        parsed = self._parse_json(raw, default=[])
        if isinstance(parsed, dict) and "questions" in parsed:
            parsed = parsed["questions"]
        if not isinstance(parsed, list) or not parsed:
            return mock_warmup_questions(ctx.competencies, count)[:count]
        normalized = normalize_warmup_questions(parsed, ctx.competencies)
        if len(normalized) < max(2, count // 3):
            return mock_warmup_questions(ctx.competencies, count)[:count]
        return normalized[:count]

    async def generate_report(self, ctx: InterviewContext) -> dict[str, Any]:
        prompt = f"""Сформируй итоговый отчёт по техническому интервью. ВЕСЬ ТЕКСТ — на русском языке.

JSON (только валидный JSON, без markdown):
{{
  "competency_scores": {{"Навык": число 0-100}},
  "strengths": ["сильная сторона на русском"],
  "weaknesses": ["слабая сторона на русском"],
  "communication_assessment": {{
    "ясность": "краткая оценка",
    "вовлечённость": "краткая оценка",
    "итог": "1-2 предложения по коммуникации"
  }},
  "code_quality_assessment": {{
    "корректность": "1-10 или словами",
    "эффективность": "оценка",
    "читаемость": "оценка",
    "итог": "1-2 предложения по коду"
  }},
  "honesty_signals": {{"работа_с_незнанием": "оценка"}},
  "confidence_level": 0.0-1.0,
  "recommendation": "reject|weak_fit|good_fit|strong_fit",
  "final_summary": "развёрнутое заключение на русском: 3-6 предложений для HR — уровень кандидата, техника, soft skills, почему такая рекомендация"
}}

Правила:
- competency_scores: ключи — названия навыков из competencies (например SQL, Python).
- Для навыков с покрытием (coverage) < 0.15 обязательно: score не выше 40, в weaknesses явно напиши «навык X не успели проверить» / «недостаточно данных по X», и в final_summary упомяни непроверенные навыки.
- recommendation: только одно из reject, weak_fit, good_fit, strong_fit. Не ставь strong_fit/good_fit, если важный навык (вес ≥25) почти не проверялся.
- Учитывай стенограмму и финальный код. Будь конкретен (примеры из интервью), не общие фразы на английском.
- Если есть мини-тест во время пауз — упомяни кратко (вес не более 15%); не пиши «MCQ» — пиши «мини-тест во время пауз».
- final_summary: понятный текст для руководителя/HR без жаргона, 3–6 предложений; отдельно укажи, сколько задач успели закрыть и какие навыки не покрыты.

ЗАПРЕЩЕНО в weaknesses и негативной коммуникации:
- «опечатки» в устной речи (STT): «Love Join» вместо LEFT JOIN и т.п. — это не ошибка кандидата.
- «переспрашивает», «невнимателен к формулировкам», если кандидат реагировал на шаблонные/пустые ответы интервьюера без новой задачи.
- Soft skills и «внимательность к формулировкам» — вне scope технического интервью.
- НЕ рекомендуй «дополнительное техническое интервью», «повторное интервью» или «провести ещё одно интервью» — выноси чёткий вердикт по имеющимся данным (reject/weak_fit/good_fit/strong_fit).

{agent_issues_from_transcript(ctx.transcript_history)}

{ctx.warmup_quiz_summary}

Формат интервью: {ctx.format_name}
{"Режим Live Coding с AI-помощником: оценивай декомпозицию, промпты и итоговый код с комментариями." if ctx.live_coding_ai_assistant else ""}
Компетенции: {json.dumps(ctx.competencies, ensure_ascii=False)}
Покрытие: {json.dumps(ctx.coverage, ensure_ascii=False)}

Стенограмма:
{json.dumps(ctx.transcript_history, ensure_ascii=False)[:15000]}

Финальный код ({ctx.language}):
```
{ctx.current_code[:8000]}
```"""
        raw = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Ты эксперт по оценке кандидатов после технического интервью. "
                        "Оцениваешь только технические навыки и код. Устная стенограмма — STT с искажениями. "
                        "Отвечай только валидным JSON. Все строковые значения — на русском языке."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        parsed = self._parse_json(
            raw,
            default={
                "recommendation": "weak_fit",
                "final_summary": "Недостаточно данных для полноценной оценки.",
                "strengths": [],
                "weaknesses": [],
                "competency_scores": {},
                "confidence_level": 0.3,
            },
        )
        return sanitize_report_data(parsed)

    @staticmethod
    def _parse_json(raw: str, default: Any) -> Any:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{") if "{" in raw else raw.find("[")
            end = raw.rfind("}") if "{" in raw else raw.rfind("]")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    pass
        return default if default is not None else None
