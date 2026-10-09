"""Поиск функций/view по упоминанию объекта в SQL (f_get_link_object + fallback)."""

import logging

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.utils.write_classifier import (
    branch_role_for_target,
    classify_write_to_table,
    is_excluded_by_suffix,
    rank_writers,
    write_roles_summary,
)

logger = logging.getLogger("gp_mcp.link_object")

_LINK_SCHEMAS = [
    settings.GP_MATERIALIZED_SCHEMA,
    settings.GP_DEFAULT_PROCEDURE_SCHEMA,
]


def _fetch_function_body(schema, function_name, need_full=False):
    """
    Тело для classify_write. Сначала left(prosrc) — быстро.
    pg_get_functiondef только если need_full (DML за пределами 50k) — иначе
    перебор десятков кандидатов с pg_get_functiondef подвешивает MCP.
    """
    rows = db_manager.fetch_all(
        """
        SELECT left(p.prosrc, 50000) AS definition,
               length(p.prosrc) AS src_len
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = :schema AND p.proname = :name
        ORDER BY p.oid LIMIT 1
        """,
        {"schema": schema, "name": function_name},
    )
    if not rows:
        return ""
    body = rows[0].get("definition") or ""
    src_len = int(rows[0].get("src_len") or 0)
    if need_full or (src_len > 50000 and not body):
        full = db_manager.fetch_all(
            """
            SELECT pg_get_functiondef(p.oid) AS definition
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = :schema AND p.proname = :name
            ORDER BY p.oid LIMIT 1
            """,
            {"schema": schema, "name": function_name},
        )
        if full and full[0].get("definition"):
            return full[0].get("definition") or body
    return body


def _call_f_get_link_object(obj_pattern, filter_schema="", filter_proname=""):
    """Вызов f_get_link_object в work (если есть в БД)."""
    fn_schema = settings.GP_DEFAULT_PROCEDURE_SCHEMA
    fn_name = getattr(settings, "GP_LINK_OBJECT_FUNCTION", "f_get_link_object")
    sql = """
        SELECT schemaname, proname
        FROM {fn_schema}.{fn_name}(:obj, :fs, :fp)
    """.format(fn_schema=fn_schema, fn_name=fn_name)
    try:
        logger.info("f_get_link_object start pat=%s", (obj_pattern or "")[:80])
        rows = db_manager.fetch_all(
            sql,
            {
                "obj": obj_pattern,
                "fs": filter_schema or "",
                "fp": filter_proname or "",
            },
        )
        logger.info("f_get_link_object done rows=%s", len(rows or []))
        return rows
    except Exception as exc:
        logger.debug("f_get_link_object unavailable: %s", exc)
        return None


def _search_link_object_inline(obj_pattern, schemas=None):
    """
    Fallback: логика f_get_link_object без temp table (только in/work).
    obj_pattern — фрагмент для оператора ~* (регистронезависимо).
    Тело не режем до 8k — иначе теряются упоминания в хвосте больших процедур.
    """
    schemas = schemas or _LINK_SCHEMAS
    pat = (obj_pattern or "").strip()
    if not pat:
        return []

    try:
        rows = db_manager.fetch_all(
            """
            SELECT schemaname, proname, kind, arguments FROM (
                SELECT
                    n.nspname AS schemaname,
                    p.proname::text AS proname,
                    'function'::text AS kind,
                    pg_get_function_identity_arguments(p.oid) AS arguments,
                    p.prosrc AS sql_code
                FROM pg_proc p
                JOIN pg_namespace n ON p.pronamespace = n.oid
                WHERE n.nspname = ANY(:schemas)
                  AND COALESCE(p.proisagg, false) = false
                  AND p.prosrc IS NOT NULL
                UNION ALL
                SELECT
                    v.schemaname::text,
                    v.viewname::text,
                    'view'::text,
                    ''::text AS arguments,
                    pg_get_viewdef(v.schemaname || '.' || v.viewname, true) AS sql_code
                FROM pg_views v
                WHERE v.schemaname = ANY(:schemas)
            ) t
            WHERE t.sql_code ~* :pat
            ORDER BY schemaname, proname
            """,
            {
                "schemas": schemas,
                "pat": pat,
            },
        )
        return rows
    except Exception as exc:
        logger.warning("inline link_object search failed: %s", exc)
        return []


def call_link_object_raw(obj_pattern, filter_schema="", filter_proname=""):
    """
    Сырой результат f_get_link_object (или inline fallback) — без DML-фильтров.
    Для get_link_object tool: отдать LLM как есть.
    """
    rows = _call_f_get_link_object(obj_pattern, filter_schema, filter_proname)
    if rows is None:
        return _search_link_object_inline(obj_pattern) or [], "inline_fallback"
    return rows or [], "f_get_link_object"


def find_referencing_objects(obj_pattern, filter_schema="", filter_proname=""):
    """
    Все функции/view in+work, где в SQL встречается obj_pattern.
    Возвращает [{schemaname, proname, kind, arguments?}, ...] без лимита.
    """
    seen = set()
    out = []

    rows = _call_f_get_link_object(obj_pattern, filter_schema, filter_proname)
    source = "f_get_link_object"
    if rows is None:
        rows = _search_link_object_inline(obj_pattern)
        source = "inline_fallback"

    for row in rows or []:
        kind = row.get("kind") or "function"
        args = row.get("arguments") or ""
        key = (row.get("schemaname"), row.get("proname"), kind, args)
        if key in seen:
            continue
        seen.add(key)
        item = {
            "schemaname": row.get("schemaname"),
            "proname": row.get("proname"),
            "kind": kind,
            "discovery": source,
        }
        if args:
            item["arguments"] = args
        out.append(item)
    return out


def search_patterns_for_table(schema, table):
    """Паттерны для ~*: bare table и qualified."""
    patterns = [table]
    qualified = "{0}.{1}".format(schema, table)
    if qualified not in patterns:
        patterns.append(qualified)
    short = schema.split("_")[-1] if schema else ""
    if short and short not in ("ext", "in", "work"):
        alt = "{0}.{1}".format(short, table)
        if alt not in patterns:
            patterns.append(alt)
    return patterns


def discover_writers_via_link_object(
    schema,
    table,
    exclude_name_suffixes=None,
    limit=None,
    return_meta=False,
):
    """
    Шаг 1–2 плана: link_object → перебор → classify_write_to_table.
    Оставляет только процедуры с DML на target schema.table.

    limit=None → без потолка по числу writers (перебираются все кандидаты).
    return_meta=True → (writers, truncated).
    """
    # 0 / None = без лимита; раньше дефолт 30 обрезал хвост
    if limit is None:
        limit = 0
    suffixes = exclude_name_suffixes or []
    candidates = {}

    for pat in search_patterns_for_table(schema, table):
        for row in find_referencing_objects(pat):
            sch = row.get("schemaname")
            name = row.get("proname")
            if row.get("kind") == "view":
                continue
            if not sch or not name:
                continue
            if is_excluded_by_suffix(name, suffixes):
                continue
            candidates[(sch, name)] = row

    writers = []
    truncated = False
    for sch, name in sorted(candidates.keys()):
        body = _fetch_function_body(sch, name)
        if not body:
            continue
        roles = classify_write_to_table(body, schema, table)
        if not roles and len(body) >= 49000:
            body = _fetch_function_body(sch, name, need_full=True)
            roles = classify_write_to_table(body, schema, table) if body else []
        if not roles:
            continue
        writers.append({
            "qualified": "{0}.{1}".format(sch, name),
            "write_roles": roles,
            "write_role": write_roles_summary(roles),
            "branch_role": branch_role_for_target(roles),
            "discovery": "link_object",
        })
        if limit and len(writers) >= limit:
            truncated = True
            logger.warning(
                "link_object: writers обрезаны лимитом %s для %s.%s",
                limit,
                schema,
                table,
            )
            break

    ranked = rank_writers(writers)
    if return_meta:
        return ranked, truncated
    return ranked


def merge_writer_lists(*lists):
    """Объединить writers по qualified, сохранить discovery."""
    merged = {}
    for writers in lists:
        for w in writers or []:
            q = w.get("qualified")
            if not q:
                continue
            if q not in merged:
                merged[q] = dict(w)
            else:
                existing = merged[q]
                if not existing.get("discovery") and w.get("discovery"):
                    existing["discovery"] = w.get("discovery")
    return rank_writers(list(merged.values()))
