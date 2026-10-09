"""Жёсткая проверка качества MCQ мини-теста: факты, дедуп по теме, безопасные правки."""
from __future__ import annotations

import re
from typing import Any


def normalize_question_text(text: str) -> str:
    t = str(text or "").strip().lower()
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)
    t = re.sub(r"диалект:\s*\w+\.?\s*", "", t)
    t = re.sub(r"[^\w\sа-яё]+", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip()
    for prefix in (
        "какой ",
        "какая ",
        "какие ",
        "что такое ",
        "что вернет ",
        "что вернёт ",
        "что выведет ",
        "что возвращает ",
        "выберите ",
        "укажите ",
        "как ",
    ):
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    return t


def question_topic_key(question: str) -> str:
    """Грубая тема вопроса — для отсечения смысловых повторов."""
    t = normalize_question_text(question)
    q = str(question or "").lower()
    rules: list[tuple[re.Pattern[str], str]] = [
        (re.compile(r"\.lower\s*\(|lower\s*\(\s*\)"), "py_str_lower"),
        (re.compile(r"\.upper\s*\("), "py_str_upper"),
        (re.compile(r"\brange\s*\("), "py_range"),
        (re.compile(r"2\s*\*\*\s*3|\*\*\s*3|возведен.*степен"), "py_pow"),
        (re.compile(r"list\.append|добавля.*конец.*списк"), "py_list_append"),
        (re.compile(r"список.*кортеж|list.*tuple|в\s+кортеж"), "py_list_to_tuple"),
        (re.compile(r"кортеж.*список|tuple.*list|в\s+список"), "py_tuple_to_list"),
        (re.compile(r"try[\s-]*except|обработк.*исключен"), "py_try_except"),
        (re.compile(r"keys\s*\(\)|ключ.*словар"), "py_dict_keys"),
        (re.compile(r"int\s*\(|цел(ое|ого)\s+числ"), "py_int"),
        (re.compile(r"list\s+comprehension|списков.*выражен"), "py_listcomp"),
        (re.compile(r"left\s+join|лев(ой|ая|ую)\s+таблиц"), "sql_left_join"),
        (re.compile(r"right\s+join|прав(ой|ая|ую)\s+таблиц"), "sql_right_join"),
        (re.compile(r"inner\s+join"), "sql_inner_join"),
        (re.compile(r"full\s+(outer\s+)?join"), "sql_full_join"),
        (re.compile(r"\bhaving\b"), "sql_having"),
        (re.compile(r"\bgroup\s+by\b"), "sql_group_by"),
        (re.compile(r"\bltrim\b|пробел.*начал|начал.*пробел"), "sql_ltrim"),
        (re.compile(r"\brtrim\b|пробел.*конц"), "sql_rtrim"),
        (re.compile(r"\btrim\b"), "sql_trim"),
        (re.compile(r"count\s*\(\s*\*"), "sql_count_star"),
        (re.compile(r"объединен.*строк|конкатен|\|\|"), "sql_concat"),
        (re.compile(r"bigint|больш.*длин"), "sql_bigint"),
        (re.compile(r"2147483647|integer\b|int4"), "sql_integer"),
        (re.compile(r"b-?tree|первичн.*ключ.*индекс"), "sql_pk_index"),
        (re.compile(r"\bcte\b|with\s+.*\bas\b|обобщённ|обобщенн"), "sql_cte"),
        (re.compile(r"row_number|dense_rank|оконн"), "sql_window"),
        (re.compile(r"serial|auto_increment|identity"), "sql_serial"),
    ]
    for pat, key in rules:
        if pat.search(q) or pat.search(t):
            return key
    # fallback: первые значимые токены
    tokens = [w for w in t.split() if len(w) > 2][:5]
    return "gen:" + "_".join(tokens) if tokens else "gen:empty"


def question_signature(item: dict[str, Any]) -> str:
    skill = str(item.get("skill", "")).strip().lower()
    question = normalize_question_text(str(item.get("question", "")))
    return f"{skill}|{question}"


def topic_signature(item: dict[str, Any]) -> str:
    skill = str(item.get("skill", "")).strip().lower()
    return f"{skill}|topic:{question_topic_key(str(item.get('question', '')))}"


def _unique_option_matches(options: list[str], pattern: re.Pattern[str]) -> list[int]:
    return [i for i, o in enumerate(options) if pattern.search(o)]


def _option_core(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().strip("'\"").lower())


def _quoted_inner(text: str) -> str | None:
    s = str(text or "").strip()
    m = re.match(r"^(['\"])(.*)\1$", s)
    if not m:
        return None
    return m.group(2)


def fix_obvious_correct_index(question: str, options: list[str], correct_index: int) -> int:
    """Безопасные правки: только если ровно один вариант однозначно подходит."""
    q = question.lower()
    n = len(options)
    if n < 2:
        return correct_index
    ci = correct_index if 0 <= correct_index < n else 0

    checks: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
        # LEFT JOIN — не любой JOIN
        (
            re.compile(r"left\s+join|лев(ой|ая|ую)\s+таблиц.*совпад|совпад.*лев(ой|ая|ую)", re.I),
            re.compile(r"^\s*left(\s+outer)?\s+join\s*$", re.I),
        ),
        (
            re.compile(r"right\s+join|прав(ой|ая|ую)\s+таблиц.*совпад", re.I),
            re.compile(r"^\s*right(\s+outer)?\s+join\s*$", re.I),
        ),
        (
            re.compile(r"inner\s+join|только\s+совпадающ", re.I),
            re.compile(r"^\s*inner\s+join\s*$", re.I),
        ),
        (
            re.compile(r"список.*кортеж|преобраз.*кортеж|в\s+кортеж", re.I),
            re.compile(r"\btuple\s*\(", re.I),
        ),
        (
            re.compile(r"кортеж.*список|преобраз.*список|в\s+список", re.I),
            re.compile(r"\blist\s*\(", re.I),
        ),
        # Сначала «оба конца» → TRIM, иначе сработает правило на «...конц» → RTRIM
        (
            re.compile(
                r"обоих\s+конц|двух\s+сторон|с\s+обоих|leading\s+and\s+trailing|"
                r"пробел[^\n]{0,40}обоих|пробел[^\n]{0,40}двух\s+сторон",
                re.I,
            ),
            re.compile(r"^\s*trim\s*\(\s*\)\s*$", re.I),
        ),
        (
            re.compile(r"пробел[^\n]{0,40}начал|начал[^\n]{0,40}пробел|\bltrim\b", re.I),
            re.compile(r"\bltrim\s*\(", re.I),
        ),
        (
            re.compile(
                r"(?<!обоих\s)(?<!двух\s)пробел[^\n]{0,40}конц|(?<!обоих\s)(?<!двух\s)\brtrim\b",
                re.I,
            ),
            re.compile(r"\brtrim\s*\(", re.I),
        ),
        (
            re.compile(r"указанн\w*\s+единиц.*дат|дат[^\n]{0,40}указанн\w*\s+единиц", re.I),
            re.compile(r"extract|date_part", re.I),
        ),
        (
            re.compile(r"цел(ое|ого)\s+числ|в\s+int\b", re.I),
            re.compile(r"\bint\s*\(", re.I),
        ),
        (
            re.compile(r"созда[^\s]*\s+таблиц|create\s+table", re.I),
            re.compile(r"\bcreate\s+table\b", re.I),
        ),
        (
            re.compile(r"удал(ить|яет)\s+таблиц|drop\s+table", re.I),
            re.compile(r"\bdrop\s+table\b", re.I),
        ),
        (
            re.compile(r"\bhaving\b|фильтрац.*групп.*агрег", re.I),
            re.compile(r"^\s*having\s*$", re.I),
        ),
        (
            re.compile(r"keys\s*\(\)|все\s+ключ", re.I),
            re.compile(r"keys\s*\(", re.I),
        ),
        (
            re.compile(r"try[\s-]*except|обработк.*исключен", re.I),
            re.compile(r"try", re.I),
        ),
    ]
    for q_re, opt_re in checks:
        if not q_re.search(q):
            continue
        hits = _unique_option_matches(options, opt_re)
        if len(hits) == 1:
            return hits[0]

    # 'ABC'.lower() → 'abc' (без пробелов и без «ошибка»)
    if re.search(r"\.lower\s*\(", q):
        for i, o in enumerate(options):
            if _quoted_inner(o) == "abc":
                return i

    # 2 ** 3 / print(2 ** 3) → 8
    if re.search(r"2\s*\*\*\s*3|print\s*\(\s*2\s*\*\*\s*3", q):
        for i, o in enumerate(options):
            if _option_core(o) == "8":
                return i

    # range(...) как тема вопроса (не listcomp / не «for x in range»)
    if re.search(r"\brange\s*\(", q) and "for " not in q and "[" not in q:
        for i, o in enumerate(options):
            core = _option_core(o)
            if "range" in core and "итератор" not in core and "list" not in core and "[" not in o:
                return i

    # BIGINT / INTEGER ranges — узкие правила
    if re.search(r"2147483647|-2147483648", q):
        hits = _unique_option_matches(options, re.compile(r"^\s*integer\s*$", re.I))
        if len(hits) == 1:
            return hits[0]
    if re.search(r"больш(ой|ую|ие)\s+длин|очень\s+больш", q) and "цел" in q:
        hits = _unique_option_matches(options, re.compile(r"^\s*bigint\s*$", re.I))
        if len(hits) == 1:
            return hits[0]

    return ci


def question_passes_quality_gate(question: str, options: list[str], correct_index: int) -> bool:
    """False — вопрос нельзя показывать кандидату."""
    if len(options) < 3:
        return False
    if correct_index < 0 or correct_index >= len(options):
        return False
    q = question.lower()
    correct = options[correct_index]
    correct_core = _option_core(correct)

    # варианты слишком похожи (без схлопывания регистра внутри кавычек)
    uniq = set()
    for o in options:
        inner = _quoted_inner(o)
        if inner is not None:
            uniq.add(("q", inner))
        else:
            uniq.add(("p", _option_core(o)))
    if len(uniq) < 3:
        return False

    # .lower() — правильный ответ должен быть abc, не ошибка
    if re.search(r"\.lower\s*\(", q):
        inner = _quoted_inner(correct)
        if inner != "abc":
            return False
        if "ошиб" in correct_core:
            return False

    # range как тема вопроса — не принимать «итератор» и «list [...]»
    if re.search(r"\brange\s*\(", q) and "for " not in q and "[" not in q:
        if "итератор" in correct_core:
            return False
        if re.search(r"\[\s*0\s*,\s*1", correct):
            return False
        if "range" not in correct_core and "объект" not in correct_core:
            return False

    # LEFT JOIN описание не должно быть FULL/INNER
    if re.search(r"лев(ой|ая|ую)\s+таблиц|left\s+join", q) and "прав" not in q:
        if not re.search(r"left(\s+outer)?\s+join", correct, re.I):
            return False

    # список→кортеж
    if re.search(r"список.*кортеж|в\s+кортеж", q):
        if not re.search(r"tuple\s*\(", correct, re.I):
            return False

    # LTRIM
    if re.search(r"пробел[^\n]{0,40}начал|начал[^\n]{0,40}пробел", q) and not re.search(
        r"обоих|двух\s+сторон", q
    ):
        if not re.search(r"ltrim\s*\(", correct, re.I):
            return False

    # TRIM с обоих концов
    if re.search(r"обоих\s+конц|двух\s+сторон|с\s+обоих", q):
        if not re.search(r"(?<![lr])trim\s*\(", correct, re.I):
            return False
        if re.search(r"[lr]trim\s*\(", correct, re.I):
            return False

    # «разница дат в указанной единице» — это EXTRACT/DATE_PART, не AGE
    if re.search(r"указанн\w*\s+единиц", q):
        if re.search(r"^\s*age\s*$", correct, re.I):
            return False
        if not re.search(r"extract|date_part", correct, re.I):
            return False

    # «ошибка» как правильный ответ — только если вопрос про ошибку/исключение
    if "ошиб" in correct_core and not re.search(r"ошибк|exception|исключен|traceback", q):
        return False

    return True


def sanitize_options(options: list[str]) -> list[str]:
    """Убрать пустые и лишние пробелы внутри/по краям кавычек."""
    cleaned: list[str] = []
    for o in options:
        s = str(o).strip()
        # "'abc '" → "'abc'"
        m = re.match(r"^(['\"])(.*)\1$", s)
        if m:
            inner = m.group(2).strip()
            s = f"{m.group(1)}{inner}{m.group(1)}"
        if s:
            cleaned.append(s)
    return cleaned
