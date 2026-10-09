"""Извлечение SQL-блоков DML для конкретной целевой таблицы."""

import re

from gp_mcp_agent.src.utils.read_classifier import is_reference_source, partition_reads
from gp_mcp_agent.src.utils.sql_table_refs import extract_table_refs


def _qualified(schema, table):
    return "{0}.{1}".format((schema or "").lower(), (table or "").lower())


def _bare(table):
    return (table or "").lower()


def _target_patterns(schema, table):
    q = re.escape(_qualified(schema, table))
    b = re.escape(_bare(table))
    qs = re.escape("{0}.{1}".format(schema or "", table or ""))
    return [q, b, qs]


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


def _parse_cte_map(sql_text):
    """WITH cte AS (...), cte2 AS (...) → {name_lower: body_sql}."""
    text = sql_text or ""
    m = re.search(r"\bwith\s+", text, flags=re.IGNORECASE)
    if not m:
        return {}

    pos = m.end()
    ctes = {}
    while pos < len(text):
        while pos < len(text) and text[pos] in " \t\n\r,":
            pos += 1
        name_m = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)", text[pos:])
        if not name_m:
            break
        name = name_m.group(1)
        pos += name_m.end()
        as_m = re.match(r"\s+as\s*\(", text[pos:], flags=re.IGNORECASE)
        if not as_m:
            break
        open_paren = pos + as_m.end() - 1
        close_paren = _balanced_paren_end(text, open_paren)
        body = text[open_paren + 1 : close_paren]
        ctes[name.lower()] = body
        pos = close_paren + 1
        rest = text[pos : pos + 30]
        if re.match(r"\s*,", rest):
            pos += re.match(r"\s*,", rest).end()
            continue
        break
    return ctes


def _prepend_attached_with_clause(full_text, dml_start, fragment):
    window_start = max(0, dml_start - 100000)
    prefix = full_text[window_start:dml_start]
    m = re.search(r"\bwith\s+", prefix, flags=re.IGNORECASE)
    if not m:
        return fragment, False
    between = prefix[m.start() :]
    if ";" in between.rstrip():
        return fragment, False
    return between + fragment, True


def _extract_statement(text, start_role, pattern):
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    start = m.start()
    rest = text[start:]
    end = len(rest)
    for sep in re.finditer(
        r";\s*|\n\s*(?:insert|update|merge|truncate|delete)\s+", rest, re.IGNORECASE
    ):
        if sep.start() > 0:
            end = min(end, sep.start() + (1 if rest[sep.start()] == ";" else 0))
            break
    fragment = rest[:end].strip()
    if fragment.endswith(";"):
        fragment = fragment[:-1].strip()
    fragment, has_with = _prepend_attached_with_clause(text, start, fragment)
    return {
        "write_role": start_role,
        "sql_fragment": fragment,
        "has_attached_with": has_with,
    }


def extract_dml_blocks_for_target(definition, schema, table):
    text = definition or ""
    if not text.strip():
        return []

    targets = _target_patterns(schema, table)
    blocks = []
    seen = set()

    stmt_defs = [
        ("insert", r"\binsert\s+into\s+(?:{t})\b"),
        ("update", r"\bupdate\s+(?:{t})\b"),
        ("merge", r"\bmerge\s+into\s+(?:{t})\b"),
        ("truncate", r"\btruncate\s+(?:table\s+)?(?:{t})\b"),
        ("delete", r"\bdelete\s+from\s+(?:{t})\b"),
    ]

    for role, tmpl in stmt_defs:
        for t in targets:
            pat = tmpl.format(t=t)
            block = _extract_statement(text, role, pat)
            if not block:
                continue
            key = block["sql_fragment"][:300].lower()
            if key in seen:
                continue
            seen.add(key)
            blocks.append(block)

    if any(b["write_role"] == "truncate" for b in blocks) and any(
        b["write_role"] == "insert" for b in blocks
    ):
        for b in blocks:
            if b["write_role"] in ("truncate", "insert"):
                b["combined_role"] = "truncate_insert"

    return blocks


def _insert_select_tail(fragment):
    m = re.search(r"\binsert\s+into\b", fragment or "", flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return ""
    after_insert = fragment[m.end() :]
    sel = re.search(r"\bselect\b", after_insert, flags=re.IGNORECASE | re.DOTALL)
    if not sel:
        return ""
    tail = after_insert[sel.start() :]
    from_m = re.search(r"\bfrom\s+", tail, flags=re.IGNORECASE | re.DOTALL)
    if not from_m:
        return ""
    return tail[from_m.start() :]


def _from_segment_before_join(sql_from_tail):
    if not sql_from_tail:
        return ""
    jm = re.search(r"\bjoin\b", sql_from_tail, flags=re.IGNORECASE)
    return sql_from_tail[: jm.start()] if jm else sql_from_tail


def _first_from_relation(sql_from_tail):
    """Первый источник после FROM (имя CTE, schema.table или alias)."""
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


def _driving_tables_in_body(body, cte_map, target_key, visited=None):
    """
    Driving table — первая физическая таблица по цепочке FROM (без JOIN).
    CTE разворачивается рекурсивно до физической таблицы.
    """
    visited = visited or set()
    from_m = re.search(r"\bfrom\s+", body or "", flags=re.IGNORECASE | re.DOTALL)
    if not from_m:
        return []

    from_tail = body[from_m.start() :]
    from_seg = _from_segment_before_join(from_tail)
    name, qualified = _first_from_relation(from_seg)

    if not name:
        return []

    if name in (cte_map or {}):
        if name in visited:
            return []
        visited = set(visited)
        visited.add(name)
        return _driving_tables_in_body(cte_map[name], cte_map, target_key, visited)

    if qualified:
        sch, tbl = qualified
        key = _qualified(sch, tbl)
        if key != target_key:
            return [(sch, tbl)]

    refs = {}
    for sch, tbl in extract_table_refs(from_seg):
        key = _qualified(sch, tbl)
        if key != target_key:
            refs[key] = (sch, tbl)
    return list(refs.values())


def _cte_chain_summary(fragment, cte_map, target_key):
    """Для каждого CTE: driving physical tables и JOIN-справочники внутри тела."""
    summary = []
    for cte_name, body in sorted((cte_map or {}).items()):
        driving = _driving_tables_in_body(body, cte_map, target_key, set())
        driving_keys = {_qualified(s, t) for s, t in driving}
        joins = {}
        for sch, tbl in extract_table_refs(body or ""):
            key = _qualified(sch, tbl)
            if key != target_key and key not in driving_keys:
                joins[key] = (sch, tbl)
        summary.append({
            "cte": cte_name,
            "driving_tables": ["{0}.{1}".format(s, t) for s, t in driving],
            "join_tables_in_cte": ["{0}.{1}".format(s, t) for s, t in joins.values()],
        })
    return summary


def _in_query_join_reads(fragment, cte_map, driving_keys, target_key):
    """Таблицы в JOIN/CTE кроме driving — не immediate upstream."""
    all_refs = {}
    for sch, tbl in extract_table_refs(fragment or ""):
        key = _qualified(sch, tbl)
        if key != target_key:
            all_refs[key] = (sch, tbl)
    for cte_name, body in (cte_map or {}).items():
        for sch, tbl in extract_table_refs(body or ""):
            key = _qualified(sch, tbl)
            if key != target_key:
                all_refs[key] = (sch, tbl)
    return [
        "{0}.{1}".format(s, t)
        for k, (s, t) in sorted(all_refs.items())
        if k not in driving_keys
    ]


def extract_driving_reads_for_target(definition, schema, table):
    """Immediate upstream: UNION-ветки INSERT, temp-таблицы, CTE."""
    from gp_mcp_agent.src.utils.sql_temp_and_union import (
        parse_temp_table_sources,
        union_branch_sources,
    )

    target_key = _qualified(schema, table)
    blocks = extract_dml_blocks_for_target(definition, schema, table)
    temp_map = parse_temp_table_sources(definition)
    driving = {}
    used_cte = False
    cte_chain = []
    union_branches = []

    for block in blocks:
        if block.get("write_role") != "insert":
            continue
        frag = block.get("sql_fragment") or ""
        full_cte = _parse_cte_map(definition or "")
        frag_cte = _parse_cte_map(frag) if block.get("has_attached_with") or re.search(
            r"\bwith\s+", frag, re.IGNORECASE
        ) else {}
        cte_map = dict(full_cte)
        cte_map.update(frag_cte)
        if cte_map:
            used_cte = True
            cte_chain = _cte_chain_summary(frag, cte_map, target_key)

        per_branch, union_tables = union_branch_sources(
            frag, temp_map, cte_map, target_key
        )
        if union_tables:
            union_branches.extend(per_branch)
            for sch, tbl in union_tables:
                key = _qualified(sch, tbl)
                driving[key] = (sch, tbl)
            continue

        insert_tail = _insert_select_tail(frag)
        if insert_tail:
            for sch, tbl in _driving_tables_in_body(insert_tail, cte_map, target_key, set()):
                key = _qualified(sch, tbl)
                driving[key] = (sch, tbl)
        else:
            for sch, tbl in _driving_tables_in_body(frag, cte_map, target_key, set()):
                key = _qualified(sch, tbl)
                driving[key] = (sch, tbl)

    result = [
        {"schema": s, "table": t, "qualified": "{0}.{1}".format(s, t)}
        for s, t in sorted(driving.values(), key=lambda x: (x[0].lower(), x[1].lower()))
    ]
    driving_keys = set(driving.keys())
    join_reads = []
    for block in blocks:
        if block.get("write_role") != "insert":
            continue
        frag = block.get("sql_fragment") or ""
        cte_map = _parse_cte_map(definition or "")
        cte_map.update(_parse_cte_map(frag) if re.search(r"\bwith\s+", frag, re.I) else {})
        join_reads.extend(_in_query_join_reads(frag, cte_map, driving_keys, target_key))

    return result, used_cte, cte_chain, sorted(set(join_reads)), union_branches, temp_map


def extract_scoped_reads_for_target(definition, schema, table):
    driving, used_cte, _, _, _, _ = extract_driving_reads_for_target(definition, schema, table)
    return driving, used_cte


def analyze_procedure_for_target(definition, schema, table):
    blocks = extract_dml_blocks_for_target(definition, schema, table)
    driving, used_cte, cte_chain, join_reads, union_branches, temp_map = (
        extract_driving_reads_for_target(definition, schema, table)
    )
    driving_qualified = [r["qualified"] for r in driving]
    data_reads, reference_reads = partition_reads(driving_qualified)
    join_data, join_ref = partition_reads(join_reads)
    reference_reads = sorted(set(reference_reads + join_ref))
    join_reads_out = [q for q in join_reads if not is_reference_source(q)]

    limitations = []
    if used_cte:
        limitations.append("cte_chain")
    if union_branches:
        limitations.append("union_all_branches")
    if temp_map:
        limitations.append("temp_tables")
    if join_reads:
        limitations.append("joins_inside_query")
    if any(b.get("has_attached_with") for b in blocks):
        limitations.append("with_before_insert")

    llm_review = True
    manual = llm_review or (len(blocks) > 0 and len(driving) == 0)

    note = (
        "data_reads_from — физические таблицы по веткам UNION ALL и цепочке "
        "CREATE TEMP TABLE … AS SELECT … FROM <physical>. "
        "Вызовы функций в SELECT (f_*) не входят в reads_from. "
        "reference_reads_from — справочники (verify_object_terminal)."
    )

    temp_lineage = [
        {"temp": k, "physical_sources": ["{0}.{1}".format(s, t) for s, t in v]}
        for k, v in sorted(temp_map.items())
    ]

    return {
        "dml_blocks": blocks,
        "reads_from": driving,
        "immediate_reads_from": data_reads,
        "reads_from_count": len(data_reads),
        "suggested_reads_from": data_reads,
        "data_reads_from": data_reads,
        "reference_reads_from": reference_reads,
        "join_reads_in_query": join_reads_out,
        "cte_chain": cte_chain,
        "union_branches": union_branches,
        "temp_table_lineage": temp_lineage,
        "heuristic_limitations": limitations,
        "llm_review_required": llm_review,
        "manual_review_required": manual,
        "dml_block_previews": [
            (b.get("sql_fragment") or "")[:4000] for b in blocks[:3]
        ],
        "analysis_note": note,
    }
