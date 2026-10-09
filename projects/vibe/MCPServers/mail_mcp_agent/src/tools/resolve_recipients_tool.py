from mail_mcp_agent.src.mail import address_book
from mail_mcp_agent.src.tools.base import BaseTool
from mail_mcp_agent.src.utils.arg_coerce import coerce_int


class ResolveRecipientsTool(BaseTool):
    name = "resolve_recipients"
    description = (
        "Поиск email по ФИО (как «Проверить имена» в Outlook на Windows). "
        "При нескольких совпадениях вернёт таблицу display_name | email — "
        "уточните to перед send_email."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "ФИО или часть имени, например Павленко Максим",
                },
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        }

    def execute(self, arguments):
        return address_book.resolve_recipients(
            arguments.get("query"),
            max_results=coerce_int(arguments.get("max_results"), 20),
        )
