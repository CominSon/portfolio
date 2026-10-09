from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool


class HealthcheckTool(BaseTool):
    name = "healthcheck"
    description = "Проверить подключение к Greenplum."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        rows = db_manager.fetch_all("SELECT now() AS server_time")
        return {"status": "ok", "result": rows}
