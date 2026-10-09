"""Tools: обновление локальных MCP Servers из wealthhub/python.git."""

from bitbucket_mcp_agent.src.git import mcp_servers_sync
from bitbucket_mcp_agent.src.tools.base import BaseTool


class UpdateMcpServersTool(BaseTool):
    name = "update_mcp_servers"
    description = (
        "Обновить локальные MCP Servers из Bitbucket "
        "(https://df-bitbucket.ca.sbrf.ru/scm/wealthhub/python.git, ветка master, "
        "папка «MCP Servers»). "
        "Вызывай сразу по фразам: «Обнови мои MCP Серверы», «обновить MCP», "
        "«синхронизировать MCP Servers». "
        "Сравнивает каждый пакет с remote, копирует изменения в U:\\MCP Servers, "
        "синхронизирует GIGACODE_MCP_RULES.txt → %USERPROFILE%\\.gigacode\\rules\\mcp.md. "
        "Для нового сервера возвращает JSON настройки GigaIDE в new_server_setup. "
        "Без подтверждения — выполнять сразу."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "local_root": {
                    "type": "string",
                    "description": (
                        "Корень MCP Servers. По умолчанию U:\\MCP Servers "
                        "или cwd процесса."
                    ),
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Только сравнить, ничего не копировать.",
                },
                "servers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Ограничить список пакетов, напр. [\"report_mcp_agent\"]. "
                        "По умолчанию — все *_mcp_agent из remote."
                    ),
                },
            },
        }

    def execute(self, arguments):
        try:
            return mcp_servers_sync.update_mcp_servers(
                local_root=arguments.get("local_root"),
                dry_run=bool(arguments.get("dry_run")),
                servers=arguments.get("servers"),
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": str(exc),
                "message": "Не удалось обновить MCP Servers: {0}".format(exc),
                "hint": (
                    "Проверьте доступ к Bitbucket (noterball), наличие "
                    "U:\\MCP Servers и папки «MCP Servers» в python.git master."
                ),
            }
