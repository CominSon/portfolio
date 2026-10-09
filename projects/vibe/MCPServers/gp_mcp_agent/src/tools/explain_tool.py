from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.sql_validator import validate_sql


class ExplainTool(BaseTool):
    name = "explain"
    description = "Построить EXPLAIN для SELECT/WITH запроса."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SELECT, WITH или EXPLAIN запрос",
                }
            },
            "required": ["sql"],
        }

    def execute(self, arguments):
        sql = arguments.get("sql", "")
        validate_sql(sql)
        clean_sql = sql.strip().rstrip(";")

        if clean_sql.lower().startswith("explain"):
            explain_sql = clean_sql
        else:
            explain_sql = "EXPLAIN {0}".format(clean_sql)

        rows = db_manager.fetch_all(explain_sql)
        plan_lines = []
        for row in rows:
            values = list(row.values())
            if values:
                plan_lines.append(str(values[0]))

        return {"plan": plan_lines}
