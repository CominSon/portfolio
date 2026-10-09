import os

from bitbucket_mcp_agent.src.git import git_runner, project_store
from bitbucket_mcp_agent.src.tools.base import BaseTool


class GetProjectPathTool(BaseTool):
    name = "get_project_path"
    description = (
        "Текущий корень git-репозитория для всех git-операций: сохранённый путь, "
        "cwd MCP или env. Если needs_set_project_path=true — спросите путь у пользователя."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        status = project_store.get_project_path_status()
        if status.get("effective_project_path"):
            try:
                status["repo"] = git_runner.get_repo_info()
            except (ValueError, RuntimeError) as exc:
                status["repo_error"] = str(exc)
        return status


class SetProjectPathTool(BaseTool):
    name = "set_project_path"
    description = (
        "Зафиксировать корень открытого в IDEA репозитория (dashboards, users_scripts и т.д.). "
        "Путь: полный U:\\... или относительный. Вызывайте при смене проекта в IDE."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Корень клона или любая папка внутри него",
                },
                "note": {
                    "type": "string",
                    "description": "Комментарий, например dashboards",
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments):
        resolved = project_store.validate_and_resolve_project_path(arguments["path"])
        root = resolved["project_path"]
        saved = project_store.set_saved_project_path(
            root,
            note=arguments.get("note"),
        )
        info = git_runner.get_repo_info()
        return {
            "ok": True,
            "message": "Корень репозитория зафиксирован для всех git tools.",
            **saved,
            **info,
        }


class UseMcpCwdAsProjectTool(BaseTool):
    name = "use_mcp_cwd_as_project"
    description = (
        "Попробовать взять корень из cwd процесса MCP (если IDE при старте сервера "
        "передала папку открытого проекта). Иначе используйте set_project_path."
    )

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        try:
            resolved = project_store.validate_and_resolve_project_path(os.getcwd())
        except ValueError as exc:
            return {
                "ok": False,
                "mcp_process_cwd": os.getcwd(),
                "message": str(exc),
                "hint": "Укажите путь через set_project_path (корень клона в IDEA).",
            }
        root = resolved["project_path"]
        saved = project_store.set_saved_project_path(root, note="from_mcp_cwd")
        info = git_runner.get_repo_info()
        return {
            "ok": True,
            "message": "Привязан cwd процесса MCP к git-репозиторию.",
            **saved,
            **info,
        }
