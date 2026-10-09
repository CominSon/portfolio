from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name

_KIND_MAP = {
    "r": "table",
    "v": "view",
    "m": "materialized_view",
    "f": "foreign_table",
    "p": "partitioned_table",
}


class GetObjectInfoTool(BaseTool):
    name = "get_object_info"
    description = (
        "Тип объекта в GP (таблица / view / matview) и подсказка, какой tool DDL вызвать дальше. "
        "Первый шаг анализа финального объекта."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string", "description": "schema.object"},
                "schema": {"type": "string"},
                "table": {"type": "string", "description": "Имя таблицы или представления"},
            },
        }

    def execute(self, arguments):
        schema, name = resolve_schema_name(arguments, name_key="table")
        db_manager.validate_schema(schema)

        rows = db_manager.fetch_all(
            """
            SELECT
                c.relkind,
                pg_catalog.pg_get_userbyid(c.relowner) AS owner,
                COALESCE(
                    pg_catalog.pg_get_userbyid(c.relowner),
                    (SELECT r.rolname FROM pg_catalog.pg_roles r WHERE r.oid = c.relowner)
                ) AS owner_resolved
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relname = :name
            """,
            {"schema": schema, "name": name},
        )

        if not rows:
            return {
                "qualified": "{0}.{1}".format(schema, name),
                "exists": False,
                "error": "Объект не найден в pg_catalog",
            }

        relkind = rows[0].get("relkind") or ""
        kind = _KIND_MAP.get(relkind, relkind or "unknown")
        owner = rows[0].get("owner_resolved") or rows[0].get("owner")

        if kind in ("view", "materialized_view"):
            ddl_tool = "get_view_ddl"
            analysis_hint = (
                "Финал — представление: сначала get_view_ddl, извлеките источники из SQL, "
                "затем find_functions_for_table для процедур, которые наполняют базовые таблицы."
            )
        else:
            ddl_tool = "get_table_ddl"
            analysis_hint = (
                "find_functions_for_table — кто использует объект; "
                "среди writers — кто наполняет; get_function → источники в коде."
            )

        return {
            "qualified": "{0}.{1}".format(schema, name),
            "schema": schema,
            "name": name,
            "exists": True,
            "relkind": relkind,
            "object_kind": kind,
            "owner": owner,
            "ddl_tool": ddl_tool,
            "analysis_hint": analysis_hint,
        }
