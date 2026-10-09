"""Извлечение schema.table из текста SQL/PLpgSQL."""

import re

from gp_mcp_agent.resources import settings

_TABLE_REF_RE = re.compile(
    r"\b([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)

_SKIP_SCHEMA_PREFIXES = frozenset({"pg_catalog", "information_schema"})


def extract_table_refs(sql_text, allowed_schemas=None, include_all_schemas=False):
    """
    allowed_schemas — фильтр для DML внутри GP (work/in/ext).
    include_all_schemas=True — для VIEW: вернуть prx_* и прочие внешние схемы.
    """
    if allowed_schemas is None:
        allowed_schemas = settings.GP_ALLOWED_SCHEMAS
    allowed_l = {s.lower(): s for s in allowed_schemas}
    found = {}
    for sch, tbl in _TABLE_REF_RE.findall(sql_text or ""):
        sch_l = sch.lower()
        if sch_l in _SKIP_SCHEMA_PREFIXES:
            continue
        if len(sch) < 3:
            continue
        if include_all_schemas or sch_l in allowed_l:
            canon_sch = allowed_l.get(sch_l, sch)
            key = "{0}.{1}".format(canon_sch.lower(), tbl.lower())
            found[key] = (canon_sch, tbl)
    return sorted(found.values(), key=lambda x: (x[0].lower(), x[1].lower()))


def format_table_refs(refs, allowed_schemas=None):
    allowed_schemas = allowed_schemas or settings.GP_ALLOWED_SCHEMAS
    allowed_l = {s.lower() for s in allowed_schemas}
    out = []
    for sch, tbl in refs:
        qualified = "{0}.{1}".format(sch, tbl)
        out.append({
            "schema": sch,
            "table": tbl,
            "qualified": qualified,
            "in_allowed_schemas": sch.lower() in allowed_l,
            "is_external": sch.lower() not in allowed_l,
        })
    return out


def is_terminal_source(schema, table):
    t = (table or "").lower()
    s = (schema or "").lower()
    return s.endswith("_in") and t.startswith("spod_")


def classify_table_role(schema, table):
    if is_terminal_source(schema, table):
        return "terminal_source"
    if (table or "").lower().startswith("smd_"):
        return "materialized_layer"
    if (schema or "").lower().endswith("_work"):
        return "work_layer"
    if (schema or "").lower().endswith("_ext"):
        return "external_layer"
    if (schema or "").lower().startswith("prx_"):
        return "external_proxy"
    return "intermediate"
