from mail_mcp_agent.src.mail import pop3_client as inbox_client
from mail_mcp_agent.src.tools.base import BaseTool
from mail_mcp_agent.src.utils.arg_coerce import coerce_int


class ListFoldersTool(BaseTool):
    name = "list_folders"
    description = "Список папок (POP3: только INBOX)."

    def input_schema(self):
        return {"type": "object", "properties": {}}

    def execute(self, arguments):
        return inbox_client.list_folders()


class ListMessagesTool(BaseTool):
    name = "list_messages"
    description = "Последние письма в папке (по умолчанию INBOX)."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "INBOX (POP3)"},
                "limit": {"type": "integer", "description": "Число писем (макс. 100)"},
                "since_days": {"type": "integer", "description": "Только за последние N дней"},
            },
        }

    def execute(self, arguments):
        folder = (arguments.get("folder") or "INBOX").strip()
        messages = inbox_client.list_messages(
            folder=folder,
            limit=coerce_int(arguments.get("limit")),
            since_days=coerce_int(arguments.get("since_days")),
        )
        return {"folder": folder, "messages": messages, "count": len(messages)}


class SearchMessagesTool(BaseTool):
    name = "search_messages"
    description = (
        "Универсальный поиск по почте: подстрока в теме, отправителе или теле письма. "
        "Пример: failed procedure, отчёт, имя коллеги."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Строка поиска"},
                "folder": {"type": "string", "description": "Папка, по умолчанию INBOX"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        }

    def execute(self, arguments):
        query = (arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query обязателен")
        folder = (arguments.get("folder") or "INBOX").strip()
        results = inbox_client.search_messages(
            query,
            folder=folder,
            max_results=coerce_int(arguments.get("max_results")),
        )
        return {"query": query, "folder": folder, "results": results, "count": len(results)}


class GetMessageTool(BaseTool):
    name = "get_message"
    description = "Полное письмо по uid и папке; опционально сохранить вложения на диск."

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "uid": {"type": "string"},
                "folder": {"type": "string"},
                "save_attachments": {"type": "boolean"},
            },
            "required": ["uid"],
        }

    def execute(self, arguments):
        uid = str(arguments.get("uid")).strip()
        folder = (arguments.get("folder") or "INBOX").strip()
        return inbox_client.get_message(
            uid,
            folder=folder,
            save_attachments=bool(arguments.get("save_attachments")),
        )
