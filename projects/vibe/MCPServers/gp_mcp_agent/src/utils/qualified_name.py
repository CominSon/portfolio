"""Разбор квалифицированных имён schema.object."""

from typing import Optional, Tuple

from gp_mcp_agent.resources import settings
from mcp_workspace_config.arg_aliases import resolve_gp_schema


def parse_schema_object(
    value,
    allowed_schemas=None,
):
    # type: (str, Optional[list]) -> Tuple[str, str]
    value = (value or "").strip()
    if not value:
        raise ValueError("Пустое имя объекта")

    if allowed_schemas is None:
        allowed_schemas = settings.GP_ALLOWED_SCHEMAS

    lowered = value.lower()
    for schema in sorted(allowed_schemas, key=len, reverse=True):
        prefix = schema.lower() + "."
        if lowered.startswith(prefix):
            obj = value[len(schema) + 1 :].strip()
            if not obj:
                raise ValueError(
                    "После схемы '{0}' не указано имя объекта".format(schema)
                )
            return schema, obj

    if "." in value:
        schema_part, obj_part = value.split(".", 1)
        schema_part = resolve_gp_schema(schema_part.strip())
        obj_part = obj_part.strip()
        if schema_part and obj_part:
            return schema_part, obj_part

    raise ValueError(
        "Ожидается формат schema.object (например work.qs_t_ukp_weeks)"
    )


def resolve_schema_name(arguments, schema_key="schema", name_key="name", qualified_key="qualified"):
    from mcp_workspace_config.arg_aliases import normalize_gp_arguments

    arguments = normalize_gp_arguments(arguments or {})
    qualified = (arguments.get(qualified_key) or "").strip()
    schema = (arguments.get(schema_key) or "").strip()
    name = (arguments.get(name_key) or "").strip()

    if qualified:
        return parse_schema_object(qualified)

    if schema and "." in schema and not name:
        return parse_schema_object(schema)

    if name and "." in name and not schema:
        return parse_schema_object(name)

    if schema and name:
        return resolve_gp_schema(schema), name

    raise ValueError(
        "Укажите qualified (work.qs_t_ukp_weeks) или schema + table. "
        "Схема: work | in | ext или полное имя."
    )
