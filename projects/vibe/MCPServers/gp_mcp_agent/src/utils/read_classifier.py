"""Классификация источников lineage: данные vs справочники/терминалы."""

import re

_REFERENCE_TABLES = frozenset({
    "business_plan",
})

_FUNCTION_NAME_RE = re.compile(r"^f_[a-z0-9_]+$", re.IGNORECASE)


def _table_part(qualified):
    parts = (qualified or "").split(".")
    return parts[-1].lower() if len(parts) >= 2 else (qualified or "").lower()


def _schema_part(qualified):
    parts = (qualified or "").split(".")
    return parts[0].lower() if len(parts) >= 2 else ""


def is_reference_source(qualified):
    """Справочник / функция / view-справочник — не ищем upstream writer."""
    tbl = _table_part(qualified)
    if _FUNCTION_NAME_RE.match(tbl):
        return True
    if tbl in _REFERENCE_TABLES:
        return True
    if tbl.endswith("_qlik"):
        return True
    # словари / справочные таблицы
    if "_dic_" in tbl or tbl.startswith("t_tbb_dic") or tbl.startswith("dic_"):
        return True
    # служебные view-справочники (не smd_ витрины)
    if tbl.startswith("v_") and "smd_" not in tbl and (
        "spr_" in tbl or "dict" in tbl or "dic_" in tbl or "create_spr" in tbl
    ):
        return True
    return False


def is_external_layer(qualified):
    sch = _schema_part(qualified)
    return sch.endswith("_ext") or ".ext." in (qualified or "").lower()


def partition_reads(qualified_list):
    """Разделить reads_from на data (трассируем) и reference (терминалы)."""
    data = []
    reference = []
    seen_d = set()
    seen_r = set()
    for q in qualified_list or []:
        q = (q or "").strip()
        if not q:
            continue
        if is_reference_source(q) or is_external_layer(q):
            if q not in seen_r:
                reference.append(q)
                seen_r.add(q)
        else:
            if q not in seen_d:
                data.append(q)
                seen_d.add(q)
    return data, reference
