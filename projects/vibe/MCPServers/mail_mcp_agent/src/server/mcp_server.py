import logging
from enum import Enum

from mail_mcp_agent.resources import settings
from mail_mcp_agent.src.server.mcp_protocol import (
    StdioTransport,
    make_error,
    make_success,
)
from mail_mcp_agent.src.server.tool_registry import ToolRegistry

logger = logging.getLogger("mail_mcp.server")


class ServerState(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    READY = "ready"


class MCPServer(object):
    def __init__(self, transport=None):
        self._transport = transport or StdioTransport()
        self._tools = ToolRegistry()
        self._state = ServerState.UNINITIALIZED
        self._negotiated_version = settings.DEFAULT_PROTOCOL_VERSION

    def run(self):
        logger.info("Старт %s v%s", settings.SERVER_NAME, settings.SERVER_VERSION)
        try:
            while True:
                try:
                    message = self._transport.read_message()
                except (ValueError, EOFError) as exc:
                    logger.warning("Пропуск битого MCP-сообщения: %s", exc)
                    continue
                if message is None:
                    break
                self._process_message(message)
        finally:
            logger.info("Остановка сервера")

    def _process_message(self, message):
        method = message.get("method")
        request_id = message.get("id")
        is_notification = "id" not in message and method is not None
        try:
            response = self._dispatch(message)
        except Exception as exc:
            logger.exception("Ошибка %s", method)
            if is_notification:
                return
            response = make_error(request_id, str(exc))
        if response is None or is_notification:
            return
        self._transport.write_message(response)

    def _dispatch(self, message):
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method in ("notifications/initialized", "initialized"):
            self._state = ServerState.READY
            return None

        if request_id is None and method:
            return None

        if method == "initialize":
            return self._handle_initialize(request_id, params)

        if self._state == ServerState.UNINITIALIZED:
            return make_error(request_id, "Сначала initialize.", code=-32002)

        handlers = {
            "ping": lambda rid, p: make_success(rid, {}),
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": lambda rid, p: make_success(rid, {"resources": []}),
            "prompts/list": lambda rid, p: make_success(rid, {"prompts": []}),
        }
        handler = handlers.get(method)
        if not handler:
            return make_error(request_id, "Метод не поддерживается: {0}".format(method), code=-32601)
        return handler(request_id, params)

    def _handle_initialize(self, request_id, params):
        client_version = params.get("protocolVersion", settings.DEFAULT_PROTOCOL_VERSION)
        if client_version in settings.SUPPORTED_PROTOCOL_VERSIONS:
            self._negotiated_version = client_version
        self._state = ServerState.INITIALIZED
        return make_success(request_id, {
            "protocolVersion": self._negotiated_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": settings.SERVER_NAME,
                "version": settings.SERVER_VERSION,
            },
                "instructions": (
                    "MCP почта omega. Первый шаг: healthcheck_mail (авто: pen_is, noterball(PPZ), "
                    "mail_login, my_email). Если my_email=null или needs_user_input=true — "
                    "спросите email у пользователя и вызовите set_my_email. "
                    "Поиск: search_messages → get_message. "
                    "Отправка: send_email, send_to_self=true. "
                    "{0}"
                ).format(settings.DOMAIN_KNOWLEDGE.strip()),
        })

    def _handle_tools_list(self, request_id, _params):
        return make_success(request_id, {"tools": self._tools.list_schemas()})

    def _handle_tools_call(self, request_id, params):
        tool_name = params.get("name")
        from mail_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments

        arguments = normalize_tool_arguments(params.get("arguments"))
        if not tool_name:
            return make_error(request_id, "Не указано имя tool", code=-32602)
        try:
            return make_success(request_id, self._tools.call(tool_name, arguments))
        except KeyError as exc:
            return make_error(request_id, str(exc), code=-32602)
        except ValueError as exc:
            err = self._tools.call_error(tool_name, str(exc), error_type="ValidationError")
            return make_success(request_id, err)
        except Exception as exc:
            logger.exception("tool %s", tool_name)
            err = self._tools.call_error(tool_name, str(exc), error_type=type(exc).__name__)
            return make_success(request_id, err)
