"""Валидация SQL без внешних парсеров."""

import re

FORBIDDEN_KEYWORDS = frozenset([
    "insert", "update", "delete", "drop",
    "truncate", "alter", "create",
    "grant", "revoke", "copy", "execute",
])

ALLOWED_START = ("select", "with", "explain")


def validate_sql(sql):
    # type: (str) -> None
    if not sql or not sql.strip():
        raise ValueError("SQL-запрос не может быть пустым")

    normalized = _normalize(sql)
    stripped = normalized.strip()

    if not stripped.startswith(ALLOWED_START):
        raise ValueError("Разрешены только SELECT, WITH и EXPLAIN")

    if ";" in stripped.rstrip(";"):
        raise ValueError("Разрешён только один SQL-оператор")

    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(r"\b{0}\b".format(re.escape(keyword)), stripped):
            raise ValueError("Запрещённая операция: {0}".format(keyword.upper()))


def _normalize(sql):
    # type: (str) -> str
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    without_line = re.sub(r"--[^\n]*", " ", without_block)
    return without_line.lower()
