"""Temp-таблицы и UNION ALL в теле PL/pgSQL-процедур."""

import re

from gp_mcp_agent.src.utils.sql_table_refs import extract_table_refs


def _from_segment_before_join(sql_from_tail):
    if not sql_from_tail:
        return ""
    jm = re.search(r"\bjoin\b", sql_from_tail, flags=re.IGNORECASE)
    return sql_from_tail[: jm.start()] if jm else sql_from_tail


def _first_from_relation(sql_from_tail):
    if not sql_from_tail:
        return None, None
    rest = re.sub(r"^\s*from\s+", "", sql_from_tail, flags=re.IGNORECASE).strip()
    if rest.startswith("("):
        return None, None
    m = re.match(
        r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:as\s+)?[a-zA-Z_][a-zA-Z0-9_]*)?",
        rest,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(2).lower(), (m.group(1), m.group(2))
    m = re.match(
        r"([a-zA-Z_][a-zA-Z0-9_]*)(?:\s+(?:as\s+)?([a-zA-Z_][a-zA-Z0-9_]*))?",
        rest,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).lower(), None
    return None, None


def parse_temp_table_sources(definition):
    """CREATE TEMP TABLE _x AS SELECT … FROM physical → {_x: [(sch,tbl),…]}."""
    text = definition or ""
    temp_map = {}
    for m in re.finditer(
        r"create\s+temp\s+table\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+as\s+",
        text,
        flags=re.IGNORECASE,
    ):
        name = m.group(1).lower()
        start = m.end()
        end = len(text)
        for stop in re.finditer(
            r";\s*(?:create\s+temp|truncate|insert|drop\s+table|end\s*;)",
            text[start:],
            flags=re.IGNORECASE,
        ):
            end = start + stop.start()
            break
        body = text[start:end]
        from_m = re.search(r"\bfrom\s+", body, flags=re.IGNORECASE | re.DOTALL)
        if not from_m:
            continue
        from_tail = body[from_m.start() :]
        from_seg = _from_segment_before_join(from_tail)
        tables = list(extract_table_refs(from_seg))
        if tables:
            temp_map[name] = tables
    return temp_map


def split_union_all(sql):
    """Разбить SELECT на ветки UNION ALL (depth=0)."""
    sql = sql or ""
    branches = []
    depth = 0
    start = 0
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            m = re.match(r"\s*union\s+all\s+", sql[i:], flags=re.IGNORECASE)
            if m:
                branches.append(sql[start:i].strip())
                i += m.end()
                start = i
                continue
        i += 1
    tail = sql[start:].strip()
    if tail:
        branches.append(tail)
    return branches


def _balanced_paren_end(text, open_pos):
    depth = 0
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(text) - 1


def _insert_select_sql(fragment):
    m = re.search(r"\binsert\s+into\b", fragment or "", flags=re.IGNORECASE)
    if not m:
        return ""
    after = fragment[m.end() :]
    sel = re.search(r"\bselect\b", after, flags=re.IGNORECASE | re.DOTALL)
    if not sel:
        return ""
    return after[sel.start() :].strip()


def _resolve_relation(name, qualified, temp_map, cte_map, target_key, visited):
    if not name:
        return []
    if name in (temp_map or {}):
        return list(temp_map[name])
    if name in (cte_map or {}):
        if name in visited:
            return []
        visited = set(visited)
        visited.add(name)
        return branch_driving_tables(cte_map[name], temp_map, cte_map, target_key)
    if qualified:
        return [qualified]
    return []


def branch_driving_tables(branch, temp_map, cte_map, target_key):
    from_m = re.search(r"\bfrom\s+", branch or "", flags=re.IGNORECASE | re.DOTALL)
    if not from_m:
        return []
    from_tail = branch[from_m.start() :]
    rest = re.sub(r"^\s*from\s+", "", from_tail, flags=re.IGNORECASE).strip()
    if rest.startswith("("):
        close = _balanced_paren_end(rest, 0)
        if close > 0:
            inner = rest[1:close]
            return branch_driving_tables("SELECT " + inner, temp_map, cte_map, target_key)
    from_seg = _from_segment_before_join(from_tail)
    name, qualified = _first_from_relation(from_seg)
    tables = _resolve_relation(name, qualified, temp_map, cte_map, target_key, set())
    if tables:
        return tables
    return list(extract_table_refs(from_seg))


def _union_sql_from_insert_select(select_sql):
    """SELECT … FROM ( union subquery ) alias → тело union внутри скобок."""
    from_m = re.search(r"\bfrom\s*\(", select_sql or "", flags=re.IGNORECASE | re.DOTALL)
    if from_m:
        open_paren = from_m.end() - 1
        close = _balanced_paren_end(select_sql, open_paren)
        if close > open_paren:
            return select_sql[open_paren + 1 : close].strip()
    return select_sql


def union_branch_sources(insert_fragment, temp_map, cte_map, target_key):
    """Физические источники по веткам UNION ALL в INSERT…SELECT."""
    select_sql = _insert_select_sql(insert_fragment)
    if not select_sql:
        return [], []

    union_sql = _union_sql_from_insert_select(select_sql)
    branches = split_union_all(union_sql)
    if len(branches) <= 1 and "union" not in union_sql.lower():
        branches = [union_sql]

    per_branch = []
    all_tables = {}
    for branch in branches:
        tables = branch_driving_tables(branch, temp_map, cte_map, target_key)
        qualified = [
            "{0}.{1}".format(s, t).lower() for s, t in tables
        ]
        per_branch.append({"branch_preview": branch[:200], "sources": qualified})
        for s, t in tables:
            key = "{0}.{1}".format(s, t).lower()
            if key != target_key:
                all_tables[key] = (s, t)
    return per_branch, list(all_tables.values())
