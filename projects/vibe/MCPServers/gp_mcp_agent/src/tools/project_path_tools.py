import os

from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils import project_store


class GetProjectPathTool(BaseTool):
    name = "get_project_path"
    description = (
        "Текущий путь открытого проекта IDEA для выгрузок CSV. "
        "Если needs_set_project_path=true — спросите путь у пользователя."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return project_store.get_project_path_status()


class SetProjectPathTool(BaseTool):
    name = "set_project_path"
    description = (
        "Зафиксировать папку открытого проекта в IDEA. "
        "CSV выгружается в <проект>/export/. Пример: U:\\BDProjects\\users_scripts."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Корень открытого проекта в IDEA",
                },
                "note": {"type": "string"},
            },
            "required": ["path"],
        }

    def execute(self, arguments):
        saved = project_store.set_saved_project_path(
            arguments["path"],
            note=arguments.get("note"),
        )
        status = project_store.get_project_path_status()
        return {
            "ok": True,
            "message": "Проект привязан. Выгрузки → export/ внутри этой папки.",
            **saved,
            **status,
        }


class UseMcpCwdAsProjectTool(BaseTool):
    name = "use_mcp_cwd_as_project"
    description = (
        "Взять cwd процесса MCP как папку проекта (если IDE передала её при старте). "
        "Иначе — set_project_path."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        try:
            saved = project_store.set_saved_project_path(os.getcwd(), note="from_mcp_cwd")
            status = project_store.get_project_path_status()
            return {
                "ok": True,
                "message": "Привязан cwd процесса MCP.",
                **saved,
                **status,
            }
        except ValueError as exc:
            return {
                "ok": False,
                "mcp_process_cwd": os.getcwd(),
                "message": str(exc),
                "hint": "Укажите путь через set_project_path.",
            }
