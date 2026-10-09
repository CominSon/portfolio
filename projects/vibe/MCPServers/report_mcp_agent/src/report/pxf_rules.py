"""Правила сопоставления smd_* ↔ PXF / p_copy и схемы."""

from report_mcp_agent.resources import settings


def split_qualified(qualified):
    q = (qualified or "").strip()
    if "." not in q:
        return "", q
    sch, name = q.split(".", 1)
    return sch.strip(), name.strip()


def is_smd_table_name(table_name):
    name = (table_name or "").strip()
    if "." in name:
        name = name.split(".")[-1]
    return name.lower().startswith(settings.SAMPLE_TABLE_PREFIX)


def is_in_schema(schema):
    sch = (schema or "").strip().lower()
    if not sch:
        return False
    if sch in ("in", settings.GP_IN_SCHEMA.lower()):
        return True
    return sch.endswith(settings.ALLOWED_SAMPLE_SCHEMA_SUFFIX)


def is_work_schema(schema):
    sch = (schema or "").strip().lower()
    if sch in ("work", settings.GP_WORK_SCHEMA.lower()):
        return True
    return sch.endswith("_work")


def is_pxf_source_candidate(qualified):
    """
    Кандидат в источник PXF: объект smd_* на схеме in.
    smd_* на work/других схемах — обычная промежуточная таблица, не PXF.
    """
    sch, name = split_qualified(qualified)
    if not is_smd_table_name(name):
        return False
    return is_in_schema(sch)


def classify_smd_object(qualified):
    """
    Классификация объекта с префиксом smd_.
    Возвращает dict: role = pxf_candidate | intermediate | needs_schema | not_smd
    """
    sch, name = split_qualified(qualified)
    if not is_smd_table_name(name):
        return {"role": "not_smd", "qualified": qualified}
    if not sch:
        return {
            "role": "needs_schema",
            "qualified": qualified,
            "name": name,
            "hint": (
                "Укажите схему для `{0}`. Если объект на `{1}` — вероятный PXF-источник; "
                "если на work/иной схеме — промежуточная таблица (не искать в PXF)."
            ).format(name, settings.GP_IN_SCHEMA),
        }
    if is_in_schema(sch):
        return {
            "role": "pxf_candidate",
            "qualified": "{0}.{1}".format(sch, name) if sch else name,
            "schema": sch,
            "name": name,
        }
    return {
        "role": "intermediate",
        "qualified": "{0}.{1}".format(sch, name),
        "schema": sch,
        "name": name,
        "hint": (
            "`{0}` — промежуточная таблица (префикс smd_ вне схемы in). "
            "Не искать в logs_pxf; продолжать пирамиду writers как для обычной таблицы."
        ).format(qualified),
    }


def validate_smd_placement(qualified):
    """
    Совместимость: раньше запрещала work.smd_*. Теперь placement не ошибка.
    Ошибка только если smd_* без схемы (нельзя классифицировать).
    """
    info = classify_smd_object(qualified)
    if info["role"] == "needs_schema":
        return info["hint"]
    return None


def strip_smd_prefix(table_name):
    """smd_is0540_bo_je_details_h → is0540_bo_je_details_h."""
    name = (table_name or "").strip()
    if "." in name:
        name = name.split(".")[-1]
    prefix = settings.SAMPLE_TABLE_PREFIX
    if name.lower().startswith(prefix):
        return name[len(prefix) :]
    return name


def pxf_lookup_name(qualified_or_table):
    """Имя для logs_pxf_table.table_name — точное, без smd_, без «похожих» алиасов."""
    return strip_smd_prefix(qualified_or_table)


def suggested_pxf_sql(qualified_smd_table, limit=20):
    name = pxf_lookup_name(qualified_smd_table)
    return (
        "SELECT table_name, status, date_start, date_end, left(logs_text, 200) AS logs_preview\n"
        "FROM {0}\n"
        "WHERE table_name = '{1}'\n"
        "ORDER BY date_start DESC NULLS LAST\n"
        "LIMIT {2}"
    ).format(settings.GP_LOGS_PXF, name.replace("'", "''"), int(limit))


def suggested_pcopy_hint(qualified_smd_table):
    bare = pxf_lookup_name(qualified_smd_table)
    return {
        "if_pxf_empty": (
            "В logs_pxf нет table_name='{0}' — ищите процедуру p_copy* на схеме in "
            "(find_functions_for_table / run_select по prosrc), затем get_procedure_schedule."
        ).format(bare),
        "typical_proc_prefix": "p_copy",
        "typical_schema": settings.GP_IN_SCHEMA,
        "target": qualified_smd_table,
    }
