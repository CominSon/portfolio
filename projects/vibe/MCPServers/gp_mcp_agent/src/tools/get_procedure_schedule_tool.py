from datetime import datetime, timedelta

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.identifier_validator import validate_identifier
from gp_mcp_agent.src.utils.procedure_schedule import summarize_procedure_schedule

_FAILED_STATUS_SQL = "status = '{0}'".format(settings.GP_LOG_STATUS_FAILED)


class GetProcedureScheduleTool(BaseTool):
    name = "get_procedure_schedule"
    description = (
        "Типичное время запуска и медиана длительности процедуры по логам планировщика "
        "(для порядка DML и схемы «во сколько что идёт»). По умолчанию 30 дней."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "procedure_name": {
                    "type": "string",
                    "description": "Имя или часть имени процедуры",
                },
                "days": {
                    "type": "integer",
                    "description": "Глубина истории в днях (по умолчанию 30)",
                },
                "only_failed": {"type": "boolean", "default": False},
            },
            "required": ["procedure_name"],
        }

    def execute(self, arguments):
        proc_filter = (arguments.get("procedure_name") or "").strip()
        if not proc_filter:
            raise ValueError("Укажите procedure_name")

        days = int(arguments.get("days") or 30)
        days = max(1, min(days, 90))
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        schema = validate_identifier(settings.GP_LOGS_SCHEMA, "schema")
        table = validate_identifier(settings.GP_LOGS_PROCEDURE_TABLE, "table")
        db_manager.validate_schema(schema)

        conditions = ["procedure_name ILIKE :proc", "date_start >= CAST(:since AS timestamp)"]
        params = {
            "proc": "%{0}%".format(proc_filter),
            "since": since,
            "limit": settings.GP_LOGS_MAX_LIMIT,
        }
        if arguments.get("only_failed"):
            conditions.append(_FAILED_STATUS_SQL)

        sql = """
            SELECT procedure_name, status, date_start, date_end
            FROM {schema}.{table}
            WHERE {where}
            ORDER BY date_start DESC NULLS LAST
            LIMIT :limit
        """.format(schema=schema, table=table, where=" AND ".join(conditions))

        rows = db_manager.fetch_all(sql, params)
        summary = summarize_procedure_schedule(rows)

        return {
            "procedure_name": proc_filter,
            "days": days,
            "summary": summary,
            "hint": (
                "summary.schedule_label (напр. «пн–пт 06:15») — на стрелки lineage.svg; "
                "typical_start_time + weekdays (ru). "
                "last_run_at / inactive — для §5 TECHNICAL.md, не для схемы."
            ),
        }
