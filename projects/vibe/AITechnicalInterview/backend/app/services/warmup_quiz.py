"""Короткие MCQ-вопросы на время ожидания STT/TTS (генерируются при создании ссылки)."""
from __future__ import annotations

import random
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.entities import Interview
from app.services.warmup_quiz_quality import (
    fix_obvious_correct_index,
    normalize_question_text,
    question_passes_quality_gate,
    question_signature as _quality_question_signature,
    question_topic_key,
    sanitize_options,
    topic_signature,
)

WARMUP_QUIZ_KEY = "warmup_quiz"
WARMUP_QUIZ_ANSWERS_KEY = "warmup_quiz_answers"
WARMUP_QUIZ_WEIGHT = 0.15  # максимум ~15% влияния на итог vs основные вопросы
WARMUP_QUIZ_INITIAL_COUNT = 100
WARMUP_QUIZ_REFILL_BATCH = 30
WARMUP_QUIZ_LLM_BATCH_SIZE = 25


def get_warmup_quiz(interview: Interview) -> list[dict[str, Any]]:
    settings = interview.ai_settings or {}
    raw = settings.get(WARMUP_QUIZ_KEY) or []
    return list(raw) if isinstance(raw, list) else []


def get_warmup_quiz_public(interview: Interview) -> list[dict[str, Any]]:
    """Вопросы без correct_index — только для UI кандидата."""
    public: list[dict[str, Any]] = []
    for item in get_warmup_quiz(interview):
        public.append(
            {
                "id": item.get("id"),
                "skill": item.get("skill", ""),
                "question": item.get("question", ""),
                "options": list(item.get("options") or []),
            }
        )
    return public


def set_warmup_quiz(interview: Interview, questions: list[dict[str, Any]]) -> None:
    settings = dict(interview.ai_settings or {})
    settings[WARMUP_QUIZ_KEY] = questions
    interview.ai_settings = settings


def _normalize_question_text_for_sig(text: str) -> str:
    return normalize_question_text(text)


def _question_signature(item: dict[str, Any]) -> str:
    return _quality_question_signature(item)


def _topic_signature(item: dict[str, Any]) -> str:
    return topic_signature(item)


def scrub_warmup_quiz_quality(interview: Interview) -> int:
    """Исправить ключи и выкинуть некачественные вопросы из уже сохранённого банка."""
    items = get_warmup_quiz(interview)
    if not items:
        return 0
    kept: list[dict[str, Any]] = []
    changed = False
    for item in items:
        question = str(item.get("question") or "")
        options = sanitize_options(list(item.get("options") or []))
        if len(options) < 3:
            changed = True
            continue
        ci = int(item.get("correct_index", 0))
        options, ci = _dedupe_options(options, ci)
        new_ci = fix_obvious_correct_index(question, options, ci)
        if not question_passes_quality_gate(question, options, new_ci):
            changed = True
            continue
        if options != list(item.get("options") or []) or new_ci != int(item.get("correct_index", 0)):
            changed = True
        item["options"] = options
        item["correct_index"] = new_ci
        kept.append(item)
    if changed or len(kept) != len(items):
        set_warmup_quiz(interview, kept)
    return len(kept)


def warmup_needs_rebalance(interview: Interview) -> bool:
    items = get_warmup_quiz(interview)
    if len(items) < 5:
        return False
    zeros = sum(1 for q in items if int(q.get("correct_index", 0)) == 0)
    return (zeros / len(items)) > 0.85


def rebalance_warmup_option_order(interview: Interview) -> int:
    """Перемешать варианты во всём банке; отбросить вопросы, не прошедшие quality gate."""
    items = get_warmup_quiz(interview)
    if not items:
        return 0
    kept: list[dict[str, Any]] = []
    for item in items:
        options = sanitize_options(list(item.get("options") or []))
        if len(options) < 2:
            continue
        question = str(item.get("question") or "")
        ci = int(item.get("correct_index", 0))
        options, ci = _dedupe_options(options, ci)
        ci = fix_obvious_correct_index(question, options, ci)
        if not question_passes_quality_gate(question, options, ci):
            continue
        new_opts, new_ci = _shuffle_mcq_options(options, ci)
        item["options"] = new_opts
        item["correct_index"] = new_ci
        kept.append(item)
    set_warmup_quiz(interview, kept)
    return len(kept)


def answered_warmup_signatures(interview: Interview) -> list[str]:
    """Сигнатуры уже показанных мини-вопросов (текст + тема)."""
    sigs: list[str] = []
    seen: set[str] = set()
    for item in get_warmup_quiz_answers(interview):
        payload = {"skill": item.get("skill", ""), "question": item.get("question", "")}
        for sig in (_question_signature(payload), _topic_signature(payload)):
            if sig and sig not in seen:
                seen.add(sig)
                sigs.append(sig)
    return sigs


def append_warmup_questions(interview: Interview, new_questions: list[dict[str, Any]]) -> int:
    """Добавить вопросы в банк без дубликатов по тексту и теме."""
    existing = get_warmup_quiz(interview)
    seen = {_question_signature(q) for q in existing}
    seen.update(_topic_signature(q) for q in existing)
    seen.update(answered_warmup_signatures(interview))
    added: list[dict[str, Any]] = []
    for item in new_questions:
        sig = _question_signature(item)
        topic = _topic_signature(item)
        if not sig or sig in seen or topic in seen:
            continue
        seen.add(sig)
        seen.add(topic)
        added.append(item)
    if not added:
        return 0
    set_warmup_quiz(interview, existing + added)
    return len(added)

def existing_questions_hint(interview: Interview, limit: int = 40) -> str:
    """Краткий список уже существующих вопросов для промпта LLM."""
    items = get_warmup_quiz(interview)[-limit:]
    if not items:
        return ""
    lines = [f"- [{q.get('skill', '?')}] {str(q.get('question', ''))[:120]}" for q in items]
    return "Уже есть вопросы (не повторяй):\n" + "\n".join(lines)


def get_warmup_quiz_answers(interview: Interview) -> list[dict[str, Any]]:
    settings = interview.ai_settings or {}
    raw = settings.get(WARMUP_QUIZ_ANSWERS_KEY) or []
    return list(raw) if isinstance(raw, list) else []


def _find_question(interview: Interview, question_id: str) -> dict[str, Any] | None:
    for item in get_warmup_quiz(interview):
        if str(item.get("id")) == str(question_id):
            return item
    return None


def record_warmup_quiz_answer(
    interview: Interview,
    *,
    question_id: str,
    selected_index: int,
    timed_out: bool = False,
) -> dict[str, Any]:
    question = _find_question(interview, question_id)
    if not question:
        raise ValueError("Вопрос не найден")

    answers = get_warmup_quiz_answers(interview)
    existing = next((a for a in answers if str(a.get("question_id")) == str(question_id)), None)
    if existing:
        return existing

    options = list(question.get("options") or [])
    correct_index = int(question.get("correct_index", -1))
    selected = int(selected_index)
    if selected < 0 or selected >= len(options):
        selected = -1

    question_text = str(question.get("question") or "")
    # Не перетираем ключ банка опасными эвристиками — только узкие безопасные правки
    correct_index = fix_obvious_correct_index(question_text, options, correct_index)

    entry = {
        "question_id": str(question_id),
        "skill": question.get("skill", ""),
        "question": question.get("question", ""),
        "selected_index": selected,
        "selected_text": options[selected] if 0 <= selected < len(options) else "",
        "correct_index": correct_index,
        "correct_text": options[correct_index] if 0 <= correct_index < len(options) else "",
        "is_correct": selected == correct_index and selected >= 0,
        "timed_out": timed_out,
        "excluded_from_score": False,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
    answers.append(entry)
    settings = dict(interview.ai_settings or {})
    settings[WARMUP_QUIZ_ANSWERS_KEY] = answers
    interview.ai_settings = settings
    return entry


def record_warmup_quiz_skip(
    interview: Interview,
    *,
    question_id: str,
    reason: str = "submit_failed",
) -> dict[str, Any]:
    """Пропуск вопроса (сбой отправки) — не влияет на итоговую оценку."""
    question = _find_question(interview, question_id)
    answers = get_warmup_quiz_answers(interview)
    existing = next((a for a in answers if str(a.get("question_id")) == str(question_id)), None)
    if existing:
        return existing

    correct_index = int((question or {}).get("correct_index", -1))
    options = list((question or {}).get("options") or [])
    if question and options:
        correct_index = fix_obvious_correct_index(
            str(question.get("question") or ""), options, correct_index
        )
    entry = {
        "question_id": str(question_id),
        "skill": (question or {}).get("skill", ""),
        "question": (question or {}).get("question", ""),
        "selected_index": -1,
        "selected_text": "",
        "correct_index": correct_index,
        "correct_text": options[correct_index] if 0 <= correct_index < len(options) else "",
        "is_correct": False,
        "timed_out": False,
        "excluded_from_score": True,
        "skip_reason": reason,
        "answered_at": datetime.now(timezone.utc).isoformat(),
    }
    answers.append(entry)
    settings = dict(interview.ai_settings or {})
    settings[WARMUP_QUIZ_ANSWERS_KEY] = answers
    interview.ai_settings = settings
    return entry


def _answers_for_score(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [a for a in answers if not a.get("excluded_from_score")]


def warmup_quiz_stats(interview: Interview) -> dict[str, Any]:
    """Только ответы, успешно сохранённые и не помеченные как пропуск."""
    answers = _answers_for_score(get_warmup_quiz_answers(interview))
    if not answers:
        return {}
    correct = sum(1 for a in answers if a.get("is_correct"))
    total = len(answers)
    return {
        "offered": total,
        "correct": correct,
        "accuracy": round(100.0 * correct / total, 1) if total else 0.0,
    }


def warmup_quiz_accuracy(interview: Interview) -> float | None:
    stats = warmup_quiz_stats(interview)
    if not stats:
        return None
    return stats["accuracy"]


def warmup_quiz_summary_for_prompt(interview: Interview) -> str:
    stats = warmup_quiz_stats(interview)
    if not stats:
        return ""
    weight_pct = int(WARMUP_QUIZ_WEIGHT * 100)
    return (
        f"Мини-тест во время пауз (озвучка/распознавание, вес ≤{weight_pct}%): "
        f"предложено {stats['offered']}, верных {stats['correct']} "
        f"({stats['accuracy']}% точность). Это не основная часть собеседования — учитывайте кратко."
    )


def _shuffle_mcq_options(options: list[str], correct_index: int) -> tuple[list[str], int]:
    """Перемешать варианты, чтобы правильный ответ не всегда был первым."""
    if len(options) < 2:
        return options, correct_index
    indexed = list(enumerate(options))
    random.shuffle(indexed)
    new_options = [text for _, text in indexed]
    new_correct = next(i for i, (orig_idx, _) in enumerate(indexed) if orig_idx == correct_index)
    return new_options, new_correct


def _dedupe_options(options: list[str], correct_index: int, *, sql_mode: bool = False) -> tuple[list[str], int]:
    """Убрать дубликаты вариантов; сохранить индекс правильного ответа."""
    seen: dict[str, int] = {}
    new_opts: list[str] = []
    new_ci = 0
    for i, opt in enumerate(options):
        stripped = opt.strip()
        if not stripped:
            continue
        if sql_mode:
            key = stripped
        elif re.match(r"^(['\"]).*\1$", stripped):
            # строковые литералы — регистр важен ('ABC' ≠ 'abc')
            key = stripped
        else:
            key = re.sub(r"\s+", " ", stripped.lower())
        if key in seen:
            if i == correct_index:
                new_ci = seen[key]
            continue
        if i == correct_index:
            new_ci = len(new_opts)
        seen[key] = len(new_opts)
        new_opts.append(stripped)
    if not new_opts:
        return options, correct_index
    if new_ci < 0 or new_ci >= len(new_opts):
        new_ci = min(max(correct_index, 0), len(new_opts) - 1)
    return new_opts, new_ci


def _fix_obvious_correct_index(question: str, options: list[str], correct_index: int) -> int:
    """Совместимость со старыми тестами — делегирует в безопасную реализацию."""
    return fix_obvious_correct_index(question, options, correct_index)


def _is_sql_skill(skill: str, question: str) -> bool:
    blob = f"{skill} {question}".lower()
    return bool(re.search(r"\bsql\b|postgres|greenplum|hive|spark|oracle|mysql", blob))


def _map_skill_to_competencies(skill: str, competencies: list[dict]) -> str:
    names = [str(c.get("skill", "")).strip() for c in competencies if c.get("skill")]
    if not names:
        return skill
    low = skill.strip().lower()
    for name in names:
        if name.lower() in low or low in name.lower():
            return name
    if _is_sql_skill(skill, "") and any("sql" in n.lower() for n in names):
        return next(n for n in names if "sql" in n.lower())
    return names[0]


def normalize_warmup_questions(raw: Any, competencies: list[dict]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    skills = [c.get("skill", "") for c in competencies if c.get("skill")]
    fallback_skill = skills[0] if skills else "General"
    normalized: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    seen_topic: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        options = sanitize_options([str(o) for o in (item.get("options") or [])])
        if len(options) < 3:
            continue
        sql_mode = _is_sql_skill(str(item.get("skill") or ""), question)
        correct_index = int(item.get("correct_index", 0))
        if correct_index < 0 or correct_index >= len(options):
            correct_index = 0
        options, correct_index = _dedupe_options(options, correct_index, sql_mode=sql_mode)
        if len(options) < 3:
            continue
        correct_index = fix_obvious_correct_index(question, options, correct_index)
        options, correct_index = _dedupe_options(options[:4], correct_index, sql_mode=sql_mode)
        if len(options) < 3:
            continue
        if not question_passes_quality_gate(question, options, correct_index):
            continue
        skill = _map_skill_to_competencies(str(item.get("skill") or fallback_skill), competencies)
        payload = {"skill": skill, "question": question}
        sig = _question_signature(payload)
        topic = _topic_signature(payload)
        if sig in seen_text or topic in seen_topic:
            continue
        seen_text.add(sig)
        seen_topic.add(topic)
        options, correct_index = _shuffle_mcq_options(options, correct_index)
        qid = str(item.get("id") or f"wq-{uuid.uuid4().hex[:8]}")
        normalized.append(
            {
                "id": qid,
                "skill": skill,
                "question": question,
                "options": options,
                "correct_index": correct_index,
            }
        )
    return normalized


def mock_warmup_questions(competencies: list[dict], count: int = 100) -> list[dict[str, Any]]:
    skills = [c.get("skill", "General") for c in competencies if c.get("skill")] or ["Python"]
    templates = [
        ("Что вернёт len([])?", ["0", "1", "None", "Ошибка"], 0),
        ("Какой функцией преобразовать строку в целое число?", ["int()", "str()", "float()", "len()"], 0),
        ("SELECT без WHERE вернёт", ["0 строк", "все строки", "ошибку", "NULL"], 1),
        ("Индекс первого элемента списка в Python", ["-1", "0", "1", "зависит"], 1),
        ("Что вернёт выражение 'ABC'.lower()?", ["'ABC'", "'abc'", "ошибка", "None"], 1),
        (
            "Что возвращает функция range(5)?",
            ["список [0,1,2,3,4]", "кортеж (0,1,2,3,4)", "объект range от 0 до 4", "число 5"],
            2,
        ),
        (
            "Какой тип JOIN возвращает все строки из левой таблицы и совпадающие из правой?",
            ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "CROSS JOIN"],
            1,
        ),
        ("Каким методом преобразовать список в кортеж?", ["list()", "set()", "tuple()", "dict()"], 2),
        (
            "Диалект: PostgreSQL. Какая функция удаляет пробелы в начале строки?",
            ["TRIM()", "LTRIM()", "RTRIM()", "REPLACE()"],
            1,
        ),
        ("Что вернёт выражение 2 ** 3?", ["6", "8", "9", "5"], 1),
        ("Какой метод словаря возвращает пары ключ-значение?", ["keys()", "values()", "items()", "get()"], 2),
        ("Какая конструкция обрабатывает исключения в Python?", ["for-in", "if-else", "try-except", "with"], 2),
        ("Диалект: PostgreSQL. Какой оператор фильтрует группы после агрегации?", ["WHERE", "HAVING", "ON", "LIMIT"], 1),
        ("Диалект: PostgreSQL. Какой тип для целых от -2147483648 до 2147483647?", ["BIGINT", "INTEGER", "SMALLINT", "NUMERIC"], 1),
        ("Что делает list.append(x)?", ["вставляет в начало", "добавляет в конец", "удаляет x", "сортирует список"], 1),
        ("HTTP 404 означает", ["успех", "редирект", "не найдено", "ошибка сервера"], 2),
        ("Git commit фиксирует", ["рабочую копию", "индекс", "снимок в истории", "удалённый репозиторий"], 2),
        ("Диалект: PostgreSQL. COUNT(*) при наличии NULL в столбце вернёт", ["число не-NULL", "число всех строк", "NULL", "0"], 1),
        ("Как получить длину строки s в Python?", ["s.size()", "len(s)", "s.length()", "count(s)"], 1),
        ("Диалект: PostgreSQL. Какой индекс по умолчанию у PRIMARY KEY?", ["Hash", "GiST", "B-tree", "BRIN"], 2),
    ]
    out: list[dict[str, Any]] = []
    for i, tpl in enumerate(templates):
        skill = skills[i % len(skills)]
        opts, ci = _shuffle_mcq_options(list(tpl[1]), tpl[2])
        out.append(
            {
                "id": f"mock-wq-{i + 1}",
                "skill": skill,
                "question": tpl[0],
                "options": opts,
                "correct_index": ci,
            }
        )
    normalized = normalize_warmup_questions(out, competencies)
    # если нужно больше — повторять не по теме, а с лёгким уникальным суффиксом нельзя;
    # лучше вернуть уникальный качественный набор
    if len(normalized) >= count:
        return normalized[:count]
    return normalized