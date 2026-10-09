from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.csv_export import write_sql_to_csv
from gp_mcp_agent.src.utils.sql_validator import validate_sql


class RunSelectTool(BaseTool):
    name = "run_select"
    description = (
        "SELECT/WITH в чат (макс. {0} строк). "
        "Полная выгрузка — export_csv=true или export_query_csv. "
        "JSON: используй -> / ->> / jsonb_array_elements, НЕ @? (не поддерживается в GP). "
        "При isError=true с retry_recommended — исправь SQL и повтори (до 3 раз)."
    ).format(settings.GP_SELECT_ROW_LIMIT)

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SELECT или WITH запрос",
                },
                "export_csv": {
                    "type": "boolean",
                    "description": "Выгрузить все строки запроса в CSV в gp_mcp_exports",
                },
                "filename_prefix": {
                    "type": "string",
                    "description": "Префикс файла при export_csv",
                },
            },
            "required": ["sql"],
        }

    def execute(self, arguments):
        sql = arguments.get("sql", "")
        validate_sql(sql)
        clean_sql = sql.strip().rstrip(";")
        export_csv = bool(arguments.get("export_csv"))
        prefix = (arguments.get("filename_prefix") or "run_select").strip()

        if export_csv:
            export_info = write_sql_to_csv(clean_sql, prefix)
            preview_rows = db_manager.fetch_all(
                "SELECT * FROM ({0}) AS _preview LIMIT {1}".format(
                    clean_sql, settings.GP_FIELD_COMPARE_PREVIEW_LIMIT
                )
            )
            export_info["preview_rows"] = preview_rows
            export_info["preview_limit"] = settings.GP_FIELD_COMPARE_PREVIEW_LIMIT
            return export_info

        wrapped = (
            "SELECT * FROM ({0}) AS _mcp_subquery LIMIT {1}".format(
                clean_sql, settings.GP_SELECT_ROW_LIMIT
            )
        )
        rows = db_manager.fetch_all(wrapped)
        return {
            "row_count": len(rows),
            "limit": settings.GP_SELECT_ROW_LIMIT,
            "rows": rows,
            "note": (
                "Для полной выгрузки используйте export_csv=true или export_query_csv."
            ),
        }
