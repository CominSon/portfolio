import json
import logging

from mail_mcp_agent.src.tools.healthcheck_tool import HealthcheckMailTool
from mail_mcp_agent.src.tools.list_project_files_tool import ListProjectFilesTool
from mail_mcp_agent.src.tools.mail_read_tools import (
    GetMessageTool,
    ListFoldersTool,
    ListMessagesTool,
    SearchMessagesTool,
)
from mail_mcp_agent.src.tools.profile_tools import GetMailProfileTool, SetMyEmailTool
from mail_mcp_agent.src.tools.resolve_recipients_tool import ResolveRecipientsTool
from mail_mcp_agent.src.tools.send_email_tool import SendEmailTool
from mail_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments
from mail_mcp_agent.src.utils.tool_errors import build_tool_error_payload

logger = logging.getLogger("mail_mcp.tools")


class ToolRegistry(object):
    def __init__(self):
        self._tools = {
            "healthcheck_mail": HealthcheckMailTool(),
            "get_mail_profile": GetMailProfileTool(),
            "set_my_email": SetMyEmailTool(),
            "list_folders": ListFoldersTool(),
            "list_messages": ListMessagesTool(),
            "search_messages": SearchMessagesTool(),
            "get_message": GetMessageTool(),
            "send_email": SendEmailTool(),
            "resolve_recipients": ResolveRecipientsTool(),
            "list_project_files": ListProjectFilesTool(),
        }

    def list_schemas(self):
        return [t.schema() for t in self._tools.values()]

    def call(self, name, arguments):
        arguments = normalize_tool_arguments(arguments)
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError("Неизвестный tool: {0}".format(name))
        logger.info("tool=%s keys=%s", name, list(arguments.keys()))
        result = tool.execute(arguments)
        text = json.dumps(result, ensure_ascii=False, default=str, indent=2)
        return {"content": [{"type": "text", "text": text}]}

    def call_error(self, tool_name, message, error_type=None, hint=None, detail=None):
        payload = build_tool_error_payload(
            tool_name, message, error_type=error_type, hint=hint, detail=detail
        )
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        return {"content": [{"type": "text", "text": text}], "isError": True}
