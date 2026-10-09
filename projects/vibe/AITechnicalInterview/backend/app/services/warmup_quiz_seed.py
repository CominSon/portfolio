"""Проверенный вручную банк MCQ — основа мини-теста (не доверяем LLM ключам)."""
from __future__ import annotations

from typing import Any


# (skill, question, options[4], correct_index)
_SEED: list[tuple[str, str, list[str], int]] = [
    # Python
    ("Python", "Что вернёт len([])?", ["0", "1", "None", "Ошибка"], 0),
    ("Python", "Какой функцией преобразовать строку в целое число?", ["str()", "int()", "float()", "len()"], 1),
    ("Python", "Что вернёт выражение 'ABC'.lower()?", ["'ABC'", "'abc'", "ошибка", "None"], 1),
    ("Python", "Что возвращает функция range(5)?", ["список [0,1,2,3,4]", "кортеж (0..4)", "объект range", "число 5"], 2),
    ("Python", "Каким методом преобразовать список в кортеж?", ["list()", "set()", "dict()", "tuple()"], 3),
    ("Python", "Что вернёт выражение 2 ** 3?", ["6", "8", "9", "5"], 1),
    ("Python", "Какая конструкция обрабатывает исключения?", ["for-in", "if-else", "try-except", "with-only"], 2),
    ("Python", "Какой метод добавляет элемент в конец списка?", ["insert()", "extend()", "append()", "add()"], 2),
    ("Python", "Индекс первого элемента списка?", ["-1", "0", "1", "зависит от ОС"], 1),
    ("Python", "Что произойдёт при int('123a')?", ["вернёт 123", "ValueError", "TypeError", "вернёт None"], 1),
    ("Python", "Чем list отличается от tuple?", ["list неизменяем", "tuple изменяем", "list изменяем, tuple нет", "разницы нет"], 2),
    ("Python", "Что вернёт bool([])?", ["True", "False", "None", "ошибка"], 1),
    ("Python", "Как получить длину строки s?", ["s.size()", "len(s)", "s.length()", "count(s)"], 1),
    ("Python", "Что делает dict.get('k', 0) если ключа нет?", ["KeyError", "вернёт 0", "вернёт None", "вернёт 'k'"], 1),
    ("Python", "Какой метод словаря возвращает пары (ключ, значение)?", ["keys()", "values()", "items()", "get()"], 2),
    ("Python", "Что вернёт [x*2 for x in range(3)]?", ["[0,2,4]", "[2,4,6]", "[0,1,2]", "range(0,6,2)"], 0),
    ("Python", "Мутабельный аргумент по умолчанию — антипаттерн. Пример?", ["def f(x=[])", "def f(x=None)", "def f(x=0)", "def f(x='')"], 0),
    ("Python", "Что вернёт 'a' * 3?", ["'aaa'", "'a3'", "ошибка", "['a','a','a']"], 0),
    ("Python", "Как открыть файл с авто-закрытием?", ["open() без with", "with open(...) as f", "file.close() сначала", "os.open"], 1),
    ("Python", "Что такое *args в сигнатуре функции?", ["именованные аргументы", "произвольные позиционные", "только kwargs", "декоратор"], 1),
    # SQL / PostgreSQL
    ("SQL", "Диалект: PostgreSQL. Какой JOIN возвращает только совпадающие строки из обеих таблиц?", ["LEFT JOIN", "INNER JOIN", "FULL JOIN", "CROSS JOIN"], 1),
    ("SQL", "Диалект: PostgreSQL. Какой JOIN возвращает все строки левой таблицы и совпадения справа?", ["INNER JOIN", "RIGHT JOIN", "LEFT JOIN", "CROSS JOIN"], 2),
    ("SQL", "Диалект: PostgreSQL. Какой оператор фильтрует группы после агрегации?", ["WHERE", "HAVING", "ON", "LIMIT"], 1),
    ("SQL", "Диалект: PostgreSQL. Какая функция удаляет пробелы с обоих концов строки?", ["LTRIM()", "RTRIM()", "TRIM()", "REPLACE()"], 2),
    ("SQL", "Диалект: PostgreSQL. Какая функция удаляет пробелы в начале строки?", ["TRIM()", "LTRIM()", "RTRIM()", "SUBSTR()"], 1),
    ("SQL", "Диалект: PostgreSQL. Как проверить, что col равен NULL?", ["col = NULL", "col IS NULL", "col == NULL", "IFNULL(col)"], 1),
    ("SQL", "Диалект: PostgreSQL. COUNT(*) при NULL в столбце считает:", ["только не-NULL", "все строки", "всегда 0", "ошибку"], 1),
    ("SQL", "Диалект: PostgreSQL. UNION и UNION ALL — в чём разница?", ["UNION ALL удаляет дубликаты", "UNION удаляет дубликаты, UNION ALL нет", "одинаковы", "UNION только для разных типов"], 1),
    ("SQL", "Диалект: PostgreSQL. Тип для JSON с индексами (бинарный)?", ["JSON", "JSONB", "TEXT", "XML"], 1),
    ("SQL", "Диалект: PostgreSQL. Индекс по умолчанию у PRIMARY KEY?", ["Hash", "GiST", "B-tree", "BRIN"], 2),
    ("SQL", "Диалект: PostgreSQL. Целые от -2147483648 до 2147483647 — тип?", ["BIGINT", "INTEGER", "SMALLINT", "NUMERIC"], 1),
    ("SQL", "Диалект: PostgreSQL. Как добавить столбец в таблицу?", ["ALTER TABLE ... ADD COLUMN", "UPDATE COLUMN", "CREATE COLUMN", "INSERT COLUMN"], 0),
    ("SQL", "Диалект: PostgreSQL. CTE задаётся конструкцией:", ["CREATE TEMP", "WITH ... AS", "SELECT INTO", "VIEW ONLY"], 1),
    ("SQL", "Диалект: PostgreSQL. Оконная нумерация строк без пропусков при ничьих?", ["RANK()", "DENSE_RANK()", "ROW_NUMBER()", "NTILE()"], 1),
    ("SQL", "Диалект: PostgreSQL. COALESCE(NULL, 'a', 'b') вернёт:", ["NULL", "'a'", "'b'", "ошибку"], 1),
    ("SQL", "Диалект: PostgreSQL. SELECT без WHERE вернёт:", ["0 строк", "все строки таблицы", "ошибку", "только NULL"], 1),
    ("SQL", "Диалект: PostgreSQL. Что делает COMMIT?", ["отменяет транзакцию", "сохраняет изменения", "блокирует таблицу", "создаёт индекс"], 1),
    ("SQL", "Диалект: PostgreSQL. SERIAL обычно используют для:", ["текста", "автоинкремента", "JSON", "массивов"], 1),
    ("SQL", "Диалект: PostgreSQL. LIKE 'a%' найдёт строки:", ["заканчиваются на a", "начинаются с a", "содержат только a", "равны a%"], 1),
    ("SQL", "Диалект: PostgreSQL. Какая функция вернёт interval между двумя timestamp?", ["DATEDIFF", "AGE", "TRIM", "NOW"], 1),
    ("SQL", "Диалект: PostgreSQL. Как извлечь часть даты в указанной единице (год/месяц)?", ["AGE", "EXTRACT / DATE_PART", "COALESCE", "UNION"], 1),
    ("SQL", "Диалект: PostgreSQL. DISTINCT в SELECT означает:", ["сортировку", "уникальные строки результата", "только NULL", "лимит 1"], 1),
    ("SQL", "Диалект: PostgreSQL. ORDER BY ... DESC — это:", ["по возрастанию", "по убыванию", "группировка", "фильтр"], 1),
    ("SQL", "Диалект: PostgreSQL. Какой оператор логического И?", ["OR", "AND", "NOT", "XOR"], 1),
    ("SQL", "Диалект: PostgreSQL. Подзапрос в FROM называют:", ["VIEW", "derived table / subquery", "TRIGGER", "INDEX"], 1),
    ("SQL", "Диалект: PostgreSQL. BETWEEN 1 AND 5 включает:", ["только 2,3,4", "1 и 5 включительно", "только 1", "ошибку"], 1),
    ("Python", "Что вернёт type([])?", ["dict", "list", "tuple", "set"], 1),
    ("Python", "Какой оператор проверяет принадлежность элементу последовательности?", ["is", "in", "as", "of"], 1),
    ("Python", "Что вернёт 7 // 2?", ["3.5", "3", "4", "ошибку"], 1),
    ("Python", "Как объединить два списка a и b без изменения a?", ["a.append(b)", "a + b", "a.extend(b)", "a |= b"], 1),
    ("Python", "Что такое None в Python?", ["пустая строка", "специальное значение «нет значения»", "0", "False только"], 1),
]


def curated_warmup_questions(competencies: list[dict], count: int = 100) -> list[dict[str, Any]]:
    """Вернуть перемешанный проверенный банк, отфильтрованный по навыкам интервью."""
    import random
    import uuid

    names = [str(c.get("skill", "")).strip() for c in competencies if c.get("skill")]
    names_l = [n.lower() for n in names]

    def skill_ok(seed_skill: str) -> bool:
        if not names_l:
            return True
        sl = seed_skill.lower()
        for n, nl in zip(names, names_l):
            if sl == nl or sl in nl or nl in sl:
                return True
            if sl == "sql" and "sql" in nl:
                return True
            if sl == "python" and "python" in nl:
                return True
        # если в вакансии только SQL — не тащим Python и наоборот, если навык есть
        return False

    pool = [row for row in _SEED if skill_ok(row[0])]
    if len(pool) < 8:
        pool = list(_SEED)

    random.shuffle(pool)
    out: list[dict[str, Any]] = []
    for skill, question, options, ci in pool[:count]:
        # привязка к имени компетенции из вакансии
        mapped = skill
        for n, nl in zip(names, names_l):
            if skill.lower() in nl or nl in skill.lower():
                mapped = n
                break
            if skill.lower() == "sql" and "sql" in nl:
                mapped = n
                break
        opts = list(options)
        indexed = list(enumerate(opts))
        random.shuffle(indexed)
        new_opts = [t for _, t in indexed]
        new_ci = next(i for i, (oi, _) in enumerate(indexed) if oi == ci)
        out.append(
            {
                "id": f"seed-{uuid.uuid4().hex[:10]}",
                "skill": mapped,
                "question": question,
                "options": new_opts,
                "correct_index": new_ci,
            }
        )
    return out
