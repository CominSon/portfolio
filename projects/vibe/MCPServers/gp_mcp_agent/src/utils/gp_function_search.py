"""Поиск функций/процедур и представлений по зависимостям от таблицы."""

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager


def search_functions_by_pattern(pattern, limit=None, exclude_name_suffixes=None):
    limit = limit or settings.GP_LINEAGE_FUNCTION_SEARCH_LIMIT
    sql = """
        SELECT
            n.nspname AS schema_name,
            p.proname AS function_name,
            pg_get_function_identity_arguments(p.oid) AS arguments,
            pg_catalog.pg_get_userbyid(p.proowner) AS owner,
            left(p.prosrc, 4000) AS definition,
            left(p.prosrc, 1500) AS source_preview
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = ANY(:schemas)
          AND COALESCE(p.proisagg, false) = false
          AND p.prosrc IS NOT NULL
          AND btrim(p.prosrc) <> ''
          AND p.prosrc ILIKE :pat
        ORDER BY n.nspname, p.proname
        LIMIT :lim
    """
    rows = db_manager.fetch_all(
        sql,
        {
            "schemas": settings.GP_ALLOWED_SCHEMAS,
            "pat": pattern,
            "lim": limit,
        },
    )
    suffixes = exclude_name_suffixes or []
    if suffixes:
        from gp_mcp_agent.src.utils.write_classifier import is_excluded_by_suffix
        rows = [
            r for r in rows
            if not is_excluded_by_suffix(r.get("function_name"), suffixes)
        ]
    for row in rows:
        row["usage_hint"] = _usage_hint(row.get("definition") or "", pattern)
    return rows


def _usage_hint(definition, pattern):
    text = (definition or "").lower()
    if "insert" in text and pattern.strip("%").lower() in text:
        return "likely_insert"
    if "update" in text and pattern.strip("%").lower() in text:
        return "likely_update"
    if "truncate" in text and pattern.strip("%").lower() in text:
        return "likely_truncate"
    if "delete" in text and pattern.strip("%").lower() in text:
        return "likely_delete"
    return "reference"


def build_search_patterns(schema, table, mode="both"):
    patterns = []
    if mode in ("qualified", "both"):
        patterns.append("%{0}.{1}%".format(schema, table))
    if mode in ("table_only", "both"):
        patterns.append("%{0}%".format(table))
        patterns.append("% {0} %".format(table))
        patterns.append("%({0}%".format(table))
        patterns.append("%\n{0}%".format(table))
    seen = set()
    out = []
    for pat in patterns:
        if pat not in seen:
            seen.add(pat)
            out.append(pat)
    return out


def search_views_for_table(schema, table, limit=None):
    """Представления, зависящие от таблицы — через каталог, без ILIKE по definition."""
    limit = limit or settings.GP_LINEAGE_FUNCTION_SEARCH_LIMIT
    params = {
        "schema": schema,
        "table": table,
        "schemas": settings.GP_ALLOWED_SCHEMAS,
        "lim": limit,
    }

    rows = _search_views_via_view_table_usage(params)
    if rows:
        return rows

    rows = _search_views_via_pg_depend(params)
    return rows


def _search_views_via_view_table_usage(params):
    try:
        return db_manager.fetch_all(
            """
            SELECT DISTINCT
                vtu.view_schema AS schema_name,
                vtu.view_name AS view_name
            FROM information_schema.view_table_usage vtu
            WHERE vtu.table_schema = :schema
              AND vtu.table_name = :table
              AND vtu.view_schema = ANY(:schemas)
            ORDER BY 1, 2
            LIMIT :lim
            """,
            params,
        )
    except Exception:
        return []


def _search_views_via_pg_depend(params):
    try:
        return db_manager.fetch_all(
            """
            SELECT DISTINCT
                dep_ns.nspname AS schema_name,
                dep_class.relname AS view_name
            FROM pg_catalog.pg_class src_class
            JOIN pg_catalog.pg_namespace src_ns
              ON src_ns.oid = src_class.relnamespace
            JOIN pg_catalog.pg_depend dep
              ON dep.refobjid = src_class.oid
            JOIN pg_catalog.pg_rewrite rw
              ON dep.classid = 'pg_rewrite'::regclass
             AND dep.objid = rw.oid
            JOIN pg_catalog.pg_class dep_class
              ON rw.ev_class = dep_class.oid
            JOIN pg_catalog.pg_namespace dep_ns
              ON dep_ns.oid = dep_class.relnamespace
            WHERE src_ns.nspname = :schema
              AND src_class.relname = :table
              AND dep_class.relkind IN ('v', 'm')
              AND dep_ns.nspname = ANY(:schemas)
            ORDER BY 1, 2
            LIMIT :lim
            """,
            params,
        )
    except Exception:
        return []


def search_functions_via_pg_depend(schema, table, limit=None, exclude_name_suffixes=None):
    """Функции с зависимостью на таблицу в pg_catalog (дополняет ILIKE-поиск)."""
    limit = limit or settings.GP_LINEAGE_FUNCTION_SEARCH_LIMIT
    try:
        rows = db_manager.fetch_all(
            """
            SELECT DISTINCT
                pn.nspname AS schema_name,
                pp.proname AS function_name,
                pg_get_function_identity_arguments(pp.oid) AS arguments,
                left(pp.prosrc, 12000) AS definition
            FROM pg_catalog.pg_class tc
            JOIN pg_catalog.pg_namespace tn ON tn.oid = tc.relnamespace
            JOIN pg_catalog.pg_depend d ON d.refobjid = tc.oid AND d.classid = 'pg_proc'::regclass
            JOIN pg_catalog.pg_proc pp ON pp.oid = d.objid
            JOIN pg_catalog.pg_namespace pn ON pn.oid = pp.pronamespace
            WHERE tn.nspname = :schema
              AND tc.relname = :table
              AND pn.nspname = ANY(:schemas)
              AND COALESCE(pp.proisagg, false) = false
              AND pp.prosrc IS NOT NULL
            ORDER BY pn.nspname, pp.proname
            LIMIT :lim
            """,
            {
                "schema": schema,
                "table": table,
                "schemas": settings.GP_ALLOWED_SCHEMAS,
                "lim": limit,
            },
        )
    except Exception:
        return []

    suffixes = exclude_name_suffixes or []
    if suffixes:
        from gp_mcp_agent.src.utils.write_classifier import is_excluded_by_suffix
        rows = [
            r for r in rows
            if not is_excluded_by_suffix(r.get("function_name"), suffixes)
        ]
    return rows


def _merge_function_rows(*row_lists):
    merged = {}
    for rows in row_lists:
        for row in rows or []:
            key = "{0}.{1}({2})".format(
                row.get("schema_name"),
                row.get("function_name"),
                row.get("arguments") or "",
            )
            merged[key] = row
    return list(merged.values())


def search_functions_for_table(schema, table, mode="both", limit=None, exclude_name_suffixes=None):
    """
    Функции по таблице: pg_depend + ILIKE, затем merge.
    Нельзя early-return только по pg_depend — иначе теряются процедуры,
    у которых зависимость не в каталоге, а только упоминание в prosrc.
    """
    # limit=0 → без LIMIT в SQL (полное покрытие); None → старый дефолт
    if limit is None:
        limit = settings.GP_LINEAGE_FUNCTION_SEARCH_LIMIT
    sql_limit = limit if limit else 500

    depend_rows = search_functions_via_pg_depend(
        schema, table, limit=sql_limit, exclude_name_suffixes=exclude_name_suffixes
    )
    sources = []
    if depend_rows:
        sources.append("pg_depend")

    patterns = []
    if mode in ("qualified", "both"):
        patterns.append("%{0}.{1}%".format(schema, table))
    if mode in ("table_only", "both"):
        patterns.append("%{0}%".format(table))

    ilike_rows = []
    for pat in patterns:
        ilike_rows.extend(
            search_functions_by_pattern(
                pat, limit=sql_limit, exclude_name_suffixes=exclude_name_suffixes
            )
        )
    if ilike_rows:
        sources.append("ilike")

    merged = _merge_function_rows(ilike_rows, depend_rows)
    return merged, sources or patterns or ["none"]
