"""Правила диалога: завершение, зацикливание, отказ от пустых «подробнее»."""
import re
from typing import Any

_END_PHRASES = (
    "закончить интервью",
    "завершить интервью",
    "закончи интервью",
    "заверши интервью",
    "можно заканчивать",
    "давайте закончим",
    "хватит вопросов",
    "end interview",
    "finish interview",
)

_CANNOT_EXPLAIN = (
    "не могу объяснить",
    "не знаю как объяснить",
    "затрудняюсь ответить",
    "не помню",
    "не уверен",
    "сложно объяснить",
    "не могу сформулировать",
)

_MOVE_ON_PHRASES = (
    "давай дальше",
    "давайте дальше",
    "идём дальше",
    "идем дальше",
    "к следующему",
    "следующий вопрос",
    "пропустим",
    "давай пропустим",
    "хватит",
    "уже объяснил",
    "всё объяснил",
    "все объяснил",
    "достаточно",
    "не буду повторять",
    "не повторяю",
    "перейдём",
    "перейдем",
)

_VAGUE_EXPLAIN_RE = re.compile(
    r"(подробн\w*\s+(объясн|раскрой|опиш)|"
    r"можете\s+подробн|"
    r"раскройте\s+(вашу\s+)?мысл|"
    r"объясните\s+(ваше\s+)?решени|"
    r"расскажите\s+подробн|"
    r"уточните\s+подробн|"
    r"explain\s+in\s+more\s+detail)",
    re.IGNORECASE,
)

_EXPLANATION_MARKERS = (
    "потому что",
    "так как",
    "использ",
    "выбрал",
    "выбрала",
    "сделал",
    "сделала",
    "работает",
    "эффективн",
    "производительн",
    "оконн",
    "подзапрос",
    "join",
    "null",
    "индекс",
    "функци",
    "запрос",
    "алгоритм",
    "сложност",
    "o(n",
    "памят",
)


def wants_end_interview(text: str) -> bool:
    t = (text or "").lower().strip()
    return any(p in t for p in _END_PHRASES)


def candidate_cannot_explain(text: str) -> bool:
    t = (text or "").lower().strip()
    return any(p in t for p in _CANNOT_EXPLAIN)


def candidate_wants_to_move_on(text: str) -> bool:
    t = (text or "").lower().strip()
    return any(p in t for p in _MOVE_ON_PHRASES)


def is_vague_explain_request(text: str) -> bool:
    return bool(_VAGUE_EXPLAIN_RE.search(text or ""))


def candidate_answer_is_substantive(text: str) -> bool:
    t = (text or "").strip()
    if not t or t.startswith("[") and "редактор" in t.lower():
        return False
    words = t.split()
    if len(words) >= 45:
        return True
    if len(t) >= 280:
        return True
    if len(words) >= 18 and any(m in t.lower() for m in _EXPLANATION_MARKERS):
        return True
    return False


def count_vague_explain_prompts(transcript_history: list[dict], *, last_n: int = 8) -> int:
    ai_msgs = [h.get("text", "") for h in transcript_history if h.get("speaker") == "ai"]
    return sum(1 for msg in ai_msgs[-last_n:] if is_vague_explain_request(msg))


def _collapse_repeated_ngrams(words: list[str], *, min_n: int = 1, max_n: int = 4, min_reps: int = 3) -> list[str]:
    """Схлопнуть подряд идущие повторы коротких фраз (например «и по и по …»)."""
    i = 0
    while i < len(words):
        collapsed = False
        for n in range(min_n, min(max_n, len(words) - i) + 1):
            phrase = words[i : i + n]
            reps = 1
            j = i + n
            while j + n <= len(words) and [w.lower() for w in words[j : j + n]] == [w.lower() for w in phrase]:
                reps += 1
                j += n
            if reps >= (2 if n <= 2 else min_reps):
                words = words[: i + n] + words[j:]
                collapsed = True
                break
        if not collapsed:
            i += 1
    return words


def collapse_stt_repetition(text: str) -> str:
    """Убрать зацикленные повторы одной фразы из STT."""
    t = (text or "").strip()
    if not t:
        return t
    parts = re.split(r"(?<=[.!?…])\s+|\n+", t)
    out: list[str] = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        if out and out[-1].lower() == p.lower():
            continue
        out.append(p)
    merged = " ".join(out)
    words = _collapse_repeated_ngrams(merged.split())
    if len(words) >= 12:
        chunk = 5
        for i in range(len(words) - chunk * 2):
            seg = " ".join(words[i : i + chunk])
            nxt = " ".join(words[i + chunk : i + chunk * 2])
            if seg.lower() == nxt.lower():
                words = words[: i + chunk] + words[i + chunk * 2 :]
                break
    return " ".join(words)


def _sql_forward_questions(recent_ai_blob: str) -> list[str]:
    pool = [
        (
            "null",
            "Приняла, не буду повторять про объяснение. Коротко: как NULL влияет на AVG и на сравнение в вашем запросе? "
            "Можно одной фразой или правкой в редакторе.",
        ),
        (
            "left join",
            "Спасибо, по этой части достаточно. Нужны ли в выборке отделы без сотрудников — что поменяете в JOIN?",
        ),
        (
            "индекс",
            "Хорошо, идём дальше. Какой индекс вы бы добавили под этот запрос и почему?",
        ),
        (
            "транзакц",
            "Перейдём к другому аспекту: что изменится в результате, если чтение идёт без изоляции в параллельной записи?",
        ),
        (
            "group by",
            "Следующий вопрос: чем отличается ваш подход от варианта с GROUP BY и HAVING для той же задачи?",
        ),
        (
            "explain",
            "Давайте про производительность: на что смотрите в плане запроса (EXPLAIN) для этого решения?",
        ),
    ]
    for keyword, question in pool:
        if keyword not in recent_ai_blob:
            return question
    return (
        "Спасибо, по текущей теме достаточно. Предложите своё улучшение кода в редакторе "
        "или коротко назовите следующий риск, который вы бы проверили на проде."
    )


def _python_forward_questions(recent_ai_blob: str) -> list[str]:
    pool = [
        ("сложност", "Приняла ответ. Какая асимптотика у вашего решения и где узкое место?"),
        ("тест", "Идём дальше: какой один тест-кейс вы бы добавили первым?"),
        ("ошибк", "Следующий вопрос: как обработаете ошибку ввода или пустые данные?"),
        ("тип", "Какие типы/контракты у аргументов и что вернёт функция на границе?"),
        ("рефактор", "Что бы вы упростили при рефакторинге этого кода?"),
    ]
    for keyword, question in pool:
        if keyword not in recent_ai_blob:
            return question
    return "Спасибо, достаточно. Покажите в редакторе небольшое улучшение или назовите один риск в коде."


def build_forward_message(
    *,
    language: str,
    remaining_minutes: int,
    transcript_history: list[dict],
    competencies: list[dict],
) -> str:
    ai_recent = " ".join(
        (h.get("text") or "").lower()
        for h in transcript_history
        if h.get("speaker") == "ai"
    )[-4000:]

    if remaining_minutes <= 8:
        skills = ", ".join(c.get("skill", "") for c in competencies if c.get("skill")) or "компетенции"
        return (
            f"Спасибо, времени осталось около {remaining_minutes} мин — не буду возвращаться к тому же. "
            f"Кратко закроем {skills}: один финальный вопрос или можете нажать «Завершить интервью»."
        )

    lang = (language or "").lower()
    if lang == "sql":
        return _sql_forward_questions(ai_recent)
    if lang in ("python", "py"):
        return _python_forward_questions(ai_recent)
    return (
        "Спасибо, по этому пункту достаточно. Перейдём к следующему аспекту задачи — "
        "ответьте кратко или измените код в редакторе."
    )


def build_dialog_directives(
    transcript_history: list[dict],
    candidate_answer: str,
    *,
    remaining_minutes: int = 60,
) -> str:
    """Доп. инструкции для LLM по истории диалога."""
    lines: list[str] = []
    answer = (candidate_answer or "").strip()
    substantive = candidate_answer_is_substantive(answer)
    move_on = candidate_wants_to_move_on(answer)
    explain_count = count_vague_explain_prompts(transcript_history)

    lines.append(
        "Время ограничено: не зацикливайтесь на одной подтеме. "
        "Максимум одно уточнение по той же задаче, затем — новый аспект или следующая задача."
    )
    lines.append(
        "ЗАПРЕЩЕНО: общие фразы «подробнее объясните решение», «раскройте мысль», "
        "«можете подробнее» без указания конкретного пробела (строка, NULL, индекс, крайний случай)."
    )

    if substantive:
        lines.append(
            "Кандидат уже дал содержательный ответ — НЕ просите повторить объяснение. "
            "Кратко отметьте суть (одна фраза) и задайте ОДИН новый конкретный вопрос по другому аспекту "
            "или переходите к следующей задаче."
        )
    if move_on or candidate_cannot_explain(answer):
        lines.append(
            "Кандидат просит идти дальше или не может объяснить — сразу смените тему/задачу. "
            "Не возвращайтесь к тому же вопросу."
        )
    if len(answer) > 800:
        lines.append(
            "Ответ длинный — сначала одно предложение резюме, затем один новый вопрос по другому аспекту."
        )
    if explain_count >= 1:
        lines.append(
            "Вы уже просили «подробнее» — повторять нельзя. Только новая подтема или следующее задание."
        )
    if explain_count >= 2:
        lines.append("Повтор объяснения запрещён: немедленно переключитесь на другую задачу.")

    if remaining_minutes <= 15:
        lines.append(
            f"Осталось ~{remaining_minutes} мин — приоритет: закрыть разные компетенции, "
            "а не углублять одну и ту же."
        )

    ai_msgs = [h.get("text", "") for h in transcript_history if h.get("speaker") == "ai"][-4:]
    if len(ai_msgs) >= 2:
        a, b = ai_msgs[-1].strip().lower(), ai_msgs[-2].strip().lower()
        if a == b or (is_vague_explain_request(a) and is_vague_explain_request(b)):
            lines.append("Похожий вопрос уже был — сформулируйте иначе или смените подтему/задачу.")

    return "\n".join(lines)


def apply_dialog_policy_to_turn(
    turn: dict[str, Any],
    *,
    transcript_history: list[dict],
    candidate_answer: str,
    language: str = "python",
    remaining_minutes: int = 60,
    competencies: list[dict] | None = None,
) -> dict[str, Any]:
    """Подменить только явные «подробнее объясните» — не трогать нормальные ответы LLM."""
    message = (turn.get("message") or "").strip()
    if not message or not is_vague_explain_request(message):
        return turn

    substantive = candidate_answer_is_substantive(candidate_answer)
    move_on = candidate_wants_to_move_on(candidate_answer)
    explain_count = count_vague_explain_prompts(transcript_history)

    if not (substantive or move_on or candidate_cannot_explain(candidate_answer) or explain_count >= 1):
        return turn

    turn["message"] = build_forward_message(
        language=language,
        remaining_minutes=remaining_minutes,
        transcript_history=transcript_history,
        competencies=competencies or [],
    )
    return turn
