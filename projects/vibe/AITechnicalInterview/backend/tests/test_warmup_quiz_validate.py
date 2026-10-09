from app.services.warmup_quiz import (
    _dedupe_options,
    _fix_obvious_correct_index,
    normalize_warmup_questions,
)
from app.services.warmup_quiz_quality import (
    fix_obvious_correct_index,
    question_passes_quality_gate,
    question_topic_key,
    sanitize_options,
)


def test_dedupe_options_removes_duplicates():
    opts = ["int()", "str()", "int()", "float()"]
    new_opts, ci = _dedupe_options(opts, 2)
    assert new_opts == ["int()", "str()", "float()"]
    assert ci == 0


def test_fix_int_conversion_question():
    q = "Какой функцией можно преобразовать строку в целое число?"
    opts = ["str()", "int()", "float()", "len()"]
    assert _fix_obvious_correct_index(q, opts, 0) == 1


def test_normalize_fixes_wrong_correct_index():
    raw = [
        {
            "question": "Какой функцией преобразовать строку в целое число?",
            "options": ["str()", "int()", "float()", "len()"],
            "correct_index": 0,
            "skill": "Python",
        }
    ]
    out = normalize_warmup_questions(raw, [{"skill": "Python"}])
    assert len(out) == 1
    assert out[0]["options"][out[0]["correct_index"]] == "int()"


def test_fix_create_table_question():
    q = "Какой командой создаётся таблица в SQL?"
    opts = ["INSERT INTO", "CREATE TABLE", "SELECT", "ALTER VIEW"]
    assert _fix_obvious_correct_index(q, opts, 0) == 1


def test_question_signature_ignores_skill_prefix():
    from app.services.warmup_quiz import _question_signature

    a = {"skill": "SQL", "question": "[SQL] Как создать таблицу?"}
    b = {"skill": "SQL", "question": "Как создать таблицу?"}
    assert _question_signature(a) == _question_signature(b)


def test_join_heuristic_does_not_pick_first_join():
    q = (
        "Какой тип JOIN возвращает все записи из левой таблицы и только совпадающие "
        "из правой, а для несовпадающих заполняет NULL?"
    )
    opts = ["FULL OUTER JOIN", "RIGHT JOIN", "INNER JOIN", "LEFT JOIN"]
    assert fix_obvious_correct_index(q, opts, 0) == 3


def test_lower_wrong_answer_rejected():
    q = "Что вернет выражение 'ABC'.lower()?"
    opts = ["'ABC'", "'abc '", "ошибка"]
    opts = sanitize_options(opts)
    # после sanitize 'abc ' → 'abc'
    ci = fix_obvious_correct_index(q, opts, 2)
    assert opts[ci].strip("'\"") == "abc"
    assert question_passes_quality_gate(q, opts, ci)


def test_lower_error_as_correct_fails_gate():
    q = "Что вернет выражение 'ABC'.lower()?"
    opts = ["'ABC'", "'abc'", "ошибка"]
    assert not question_passes_quality_gate(q, opts, 2)


def test_range_iterator_fails_gate():
    q = "Что возвращает функция range(5)?"
    opts = ["число 5", "список [0,1,2,3,4]", "кортеж (0,1,2,3,4)", "итератор от 0 до 4"]
    assert not question_passes_quality_gate(q, opts, 3)


def test_range_object_passes():
    q = "Что возвращает функция range(5)?"
    opts = ["число 5", "список [0,1,2,3,4]", "кортеж (0,1,2,3,4)", "объект range от 0 до 4"]
    assert question_passes_quality_gate(q, opts, 3)


def test_tuple_not_list():
    q = "Каким методом можно преобразовать список в кортеж?"
    opts = ["str()", "set()", "list()", "tuple()"]
    assert fix_obvious_correct_index(q, opts, 2) == 3


def test_ltrim_not_trim():
    q = "Диалект: PostgreSQL. Какая функция удаляет лишние пробелы в начале строки?"
    opts = ["LTRIM()", "RTRIM()", "REPLACE()", "TRIM()"]
    assert fix_obvious_correct_index(q, opts, 3) == 0


def test_topic_dedupe_pow():
    assert question_topic_key("Что вернет выражение 2 ** 3?") == question_topic_key(
        "Что выведет print(2 ** 3)?"
    )


def test_normalize_drops_bad_and_near_dupes():
    raw = [
        {
            "skill": "Python",
            "question": "Что вернет выражение 'ABC'.lower()?",
            "options": ["'ABC'", "'abc '", "ошибка", "None"],
            "correct_index": 2,
        },
        {
            "skill": "Python",
            "question": "Что вернет выражение 2 ** 3?",
            "options": ["6", "8", "9", "5"],
            "correct_index": 1,
        },
        {
            "skill": "Python",
            "question": "Что выведет print(2 ** 3)?",
            "options": ["8", "9", "5", "6"],
            "correct_index": 0,
        },
        {
            "skill": "SQL",
            "question": "Какой тип JOIN возвращает все строки из левой таблицы и совпадающие из правой?",
            "options": ["INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "FULL OUTER JOIN"],
            "correct_index": 3,
        },
    ]
    out = normalize_warmup_questions(raw, [{"skill": "Python"}, {"skill": "SQL"}])
    questions = [x["question"] for x in out]
    # lower исправлен и пропущен; pow — один; left join исправлен
    assert any("lower" in q for q in questions)
    assert sum("2 ** 3" in q or "2**3" in q.replace(" ", "") for q in questions) <= 1
    left = next(x for x in out if "JOIN" in x["question"] or "join" in x["question"].lower())
    assert left["options"][left["correct_index"]].upper().startswith("LEFT")
