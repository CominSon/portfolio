from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name


class GetColumnsTool(BaseTool):
    name = "get_columns"
    description = (
        "Список колонок таблицы. Можно qualified: schema.table "
        "(например s_grnplm_ld_blago_ubhq_in.logs_procedure)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string", "description": "schema.table"},
                "schema": {"type": "string", "description": "Имя схемы"},
                "table": {"type": "string", "description": "Имя таблицы"},
            },
        }

    def execute(self, arguments):
        schema, table = resolve_schema_name(arguments, name_key="table")

        db_manager.validate_schema(schema)

        columns = db_manager.fetch_all(
            """
            SELECT ordinal_position, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
            ORDER BY ordinal_position
            """,
            {"schema": schema, "table": table},
        )

        exists = db_manager.table_exists(schema, table)
        return {
            "schema": schema,
            "table": table,
            "exists": exists,
            "columns": columns,
            "column_count": len(columns),
        }
