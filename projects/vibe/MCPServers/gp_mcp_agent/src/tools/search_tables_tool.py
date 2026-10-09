from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.arg_coerce import coerce_int
from gp_mcp_agent.src.utils.qualified_name import parse_schema_object


class SearchTablesTool(BaseTool):
    name = "search_tables"
    description = (
        "Найти таблицы по части имени. Поддерживается schema.table — "
        "поиск таблицы в указанной схеме."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Часть имени или schema.table",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Макс. число результатов (по умолчанию 50, макс. 200)",
                },
            },
            "required": ["name"],
        }

    def execute(self, arguments):
        name = arguments.get("name", "").strip()
        if not name:
            raise ValueError("Параметр 'name' обязателен")

        limit = coerce_int(arguments.get("max_results"), settings.GP_SEARCH_TABLES_LIMIT)
        limit = min(max(limit, 1), settings.GP_SEARCH_TABLES_MAX_LIMIT)

        schema_filter = None
        table_pattern = name
        if "." in name:
            try:
                schema_filter, table_pattern = parse_schema_object(name)
                db_manager.validate_schema(schema_filter)
            except ValueError:
                schema_filter = None
                table_pattern = name

        if schema_filter:
            rows = db_manager.fetch_all(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = :schema
                  AND table_name ILIKE :pattern
                ORDER BY table_name
                LIMIT :limit
                """,
                {
                    "schema": schema_filter,
                    "pattern": "%{0}%".format(table_pattern),
                    "limit": limit,
                },
            )
        else:
            rows = db_manager.fetch_all(
                """
                SELECT table_schema, table_name, table_type
                FROM information_schema.tables
                WHERE table_schema = ANY(:schemas)
                  AND table_name ILIKE :pattern
                ORDER BY table_schema, table_name
                LIMIT :limit
                """,
                {
                    "schemas": settings.GP_ALLOWED_SCHEMAS,
                    "pattern": "%{0}%".format(table_pattern),
                    "limit": limit,
                },
            )

        return {
            "tables": rows,
            "count": len(rows),
            "max_results": limit,
            "limit_reached": len(rows) >= limit,
            "parsed_schema": schema_filter,
            "parsed_table_pattern": table_pattern,
        }
