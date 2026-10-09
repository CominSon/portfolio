"""Классификация DML-операций процедуры над таблицей."""

import re

# Все модифицирующие операции равнозначны для построения графа зависимостей
MUTATION_ROLES = frozenset({
    "truncate_insert",
    "truncate",
    "insert",
    "merge",
    "update",
    "delete",
})


def is_excluded_by_suffix(name, suffixes):
    """Исключение по суффиксу имени — только если передано в запросе."""
    if not suffixes:
        return False
    n = (name or "").lower()
    for suf in suffixes:
        s = (suf or "").lower()
        if s and n.endswith(s):
            return True
    return False


def _targets_table(text, schema, table):
    qualified = "{0}.{1}".format((schema or "").lower(), (table or "").lower())
    bare = (table or "").lower()
    return qualified, bare


def classify_write_to_table(definition, schema, table):
    """
    Какие модифицирующие операции процедура выполняет над target.
    Возвращает список ролей (может быть несколько, напр. truncate + insert).
  Пустой список — только чтение или упоминание.
    """
    text = (definition or "").lower()
    if not text:
        return []

    qualified, bare = _targets_table(text, schema, table)
    roles = []

    if re.search(r"\btruncate\s+(?:table\s+)?" + re.escape(qualified), text) or re.search(
        r"\btruncate\s+(?:table\s+)?" + re.escape(bare) + r"\b", text
    ):
        roles.append("truncate")

    if re.search(r"\binsert\s+into\s+" + re.escape(qualified), text) or re.search(
        r"\binsert\s+into\s+" + re.escape(bare) + r"\b", text
    ):
        roles.append("insert")

    if re.search(r"\bmerge\s+into\s+" + re.escape(qualified), text) or re.search(
        r"\bmerge\s+into\s+" + re.escape(bare) + r"\b", text
    ):
        roles.append("merge")

    if re.search(r"\bupdate\s+" + re.escape(qualified), text) or re.search(
        r"\bupdate\s+" + re.escape(bare) + r"\b", text
    ):
        roles.append("update")

    if re.search(r"\bdelete\s+from\s+" + re.escape(qualified), text) or re.search(
        r"\bdelete\s+from\s+" + re.escape(bare) + r"\b", text
    ):
        roles.append("delete")

    if "truncate" in roles and "insert" in roles:
        roles = [r for r in roles if r not in ("truncate", "insert")]
        roles.insert(0, "truncate_insert")

    return roles


def write_roles_summary(roles):
    """Краткая строка для отображения."""
    if not roles:
        return None
    return "+".join(roles)


def writer_priority_score(roles):
    """INSERT-ветки приоритетнее UPDATE-дополнений."""
    if not roles:
        return 0
    scores = []
    for role in roles:
        scores.append({
            "truncate_insert": 100,
            "insert": 90,
            "merge": 80,
            "truncate": 75,
            "delete": 50,
            "update": 40,
        }.get(role, 0))
    return max(scores)


def branch_role_for_target(roles):
    """
    primary — основное наполнение (insert/truncate/merge).
    supplement — update-дополнение к уже наполненной таблице.
    parallel — прочие ветки.
    """
    score = writer_priority_score(roles)
    if score >= 75:
        return "primary"
    if roles and all(r == "update" for r in roles):
        return "supplement"
    if "update" in (roles or []):
        return "supplement"
    return "parallel"


def rank_writers(writers):
    """Сортировка: primary перед supplement, выше priority_score."""
    def key(w):
        roles = w.get("write_roles") or []
        br = w.get("branch_role") or branch_role_for_target(roles)
        br_order = {"primary": 0, "parallel": 1, "supplement": 2}.get(br, 3)
        return (br_order, -writer_priority_score(roles), w.get("function_name") or "")

    return sorted(writers, key=key)


def pick_suggested_writer(candidates):
    """Предпочтение INSERT-ветке над UPDATE-дополнением."""
    ranked = rank_writers(candidates)
    return ranked[0] if ranked else None


def resolve_exclude_suffixes(exclude_name_suffixes=None, exclude_dtl=False):
    suffixes = list(exclude_name_suffixes or [])
    if exclude_dtl and "_dtl" not in [s.lower() for s in suffixes]:
        suffixes.append("_dtl")
    return suffixes
