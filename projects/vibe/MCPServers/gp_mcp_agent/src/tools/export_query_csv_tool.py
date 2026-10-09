from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.csv_export import write_sql_to_csv
from gp_mcp_agent.src.utils.xlsx_export import write_sql_to_xlsx
from gp_mcp_agent.src.utils.sql_validator import validate_sql


class ExportQueryCsvTool(BaseTool):
    name = "export_query_csv"
    description = (
        "Выполнить SELECT/WITH и выгрузить все строки в файл (CSV или XLSX). "
        "XLSX — корректные типы колонок в Excel (ID как текст, даты как даты). "
        "Файл в <проект>/export/."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SELECT или WITH запрос",
                },
                "filename_prefix": {
                    "type": "string",
                    "description": "Префикс имени файла (опционально)",
                },
                "format": {
                    "type": "string",
                    "description": "csv или xlsx (по умолчанию csv)",
                },
            },
            "required": ["sql"],
        }

    def execute(self, arguments):
        sql = (arguments.get("sql") or "").strip()
        if not sql:
            raise ValueError("Параметр sql обязателен")

        validate_sql(sql)
        clean_sql = sql.strip().rstrip(";")
        prefix = (arguments.get("filename_prefix") or "query").strip() or "query"
        fmt = (arguments.get("format") or "csv").strip().lower()

        if fmt in ("xlsx", "excel"):
            return write_sql_to_xlsx(clean_sql, prefix)
        return write_sql_to_csv(clean_sql, prefix)
