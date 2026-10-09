from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.pg_stat_activity_sql import fetch_user_sessions
from gp_mcp_agent.src.utils.session_report import build_session_report

SCOPE_SELF = "self"
SCOPE_SCHEDULER = "scheduler"


class ListSessionsTool(BaseTool):
    name = "list_sessions"
    description = (
        "Таблица сессий со столбцом state (обязательно). "
        "scope=self — текущая УЗ подключения к БД (кто спрашивает). "
        "scope=scheduler — УЗ планировщика {0} ({1}), активные процессы "
        "в основном пуле (manage_backend, «что в планировщиках»). "
        "Не путать: «мои запросы» / «моя УЗ» = self; "
        "«Максима» / «Павленко» / «планировщик» / «18764734» = scheduler."
    ).format(
        settings.GP_BACKEND_USER,
        settings.GP_SCHEDULER_DISPLAY_NAME,
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": [SCOPE_SELF, SCOPE_SCHEDULER],
                },
                "include_idle": {
                    "type": "boolean",
                    "description": "Для self: включить idle/idle in transaction",
                },
            },
            "required": ["scope"],
        }

    def execute(self, arguments):
        scope = (arguments.get("scope") or SCOPE_SELF).strip().lower()
        include_idle = bool(arguments.get("include_idle"))

        if scope == SCOPE_SCHEDULER:
            return self._scheduler_sessions()
        if scope == SCOPE_SELF:
            return self._self_sessions(include_idle)
        raise ValueError("scope должен быть self или scheduler")

    @staticmethod
    def _scheduler_sessions():
        sql = "SELECT * FROM {0}.{1}(:action, NULL::int4)".format(
            settings.GP_MANAGE_BACKEND_SCHEMA,
            settings.GP_MANAGE_BACKEND_FUNCTION,
        )
        rows = db_manager.fetch_all(sql, {"action": "S"})
        return build_session_report(
            scope_key=SCOPE_SCHEDULER,
            scope_label="Планировщик: {0} — {1}".format(
                settings.GP_BACKEND_USER,
                settings.GP_SCHEDULER_DISPLAY_NAME,
            ),
            username=settings.GP_BACKEND_USER,
            rows=rows,
            source="{0}.{1}('S')".format(
                settings.GP_MANAGE_BACKEND_SCHEMA,
                settings.GP_MANAGE_BACKEND_FUNCTION,
            ),
        )

    @staticmethod
    def _self_sessions(include_idle):
        current_user = db_manager.get_current_user()
        if include_idle:
            state_filter = "state IN ('active','idle','idle in transaction','waiting')"
        else:
            state_filter = "state = 'active'"

        rows, source = fetch_user_sessions(current_user, state_filter)

        return build_session_report(
            scope_key=SCOPE_SELF,
            scope_label="Текущая УЗ подключения (кто спрашивает)",
            username=current_user,
            rows=rows,
            source=source,
        )
