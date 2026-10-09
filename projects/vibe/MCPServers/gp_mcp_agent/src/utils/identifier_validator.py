"""Проверка имён SQL-объектов (без sqlparse)."""

import re

_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_identifier(name, kind="identifier"):
    # type: (str, str) -> str
    name = (name or "").strip()
    if not name or not _IDENT_RE.match(name):
        raise ValueError(
            "Некорректное имя {0}: '{1}'".format(kind, name)
        )
    return name
