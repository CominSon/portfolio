import logging
from enum import Enum

from report_mcp_agent.resources import settings
from report_mcp_agent.src.server.mcp_protocol import (
    StdioTransport,
    make_error,
    make_success,
)
from report_mcp_agent.src.server.tool_registry import ToolRegistry

logger = logging.getLogger("report_mcp.server")


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
            logger.info("Клиент отправил initialized, сервер готов к работе")
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
        if handler is None:
            return make_error(request_id, "Метод не поддерживается: {0}".format(method), code=-32601)
        return handler(request_id, params)

    def _handle_initialize(self, request_id, params):
        client = (params.get("clientInfo") or {})
        logger.info(
            "initialize: client=%s %s",
            client.get("name"),
            client.get("version"),
        )
        requested = params.get("protocolVersion") or settings.DEFAULT_PROTOCOL_VERSION
        if requested in settings.SUPPORTED_PROTOCOL_VERSIONS:
            self._negotiated_version = requested
        else:
            self._negotiated_version = settings.DEFAULT_PROTOCOL_VERSION
        self._state = ServerState.INITIALIZED
        return make_success(
            request_id,
            {
                "protocolVersion": self._negotiated_version,
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": settings.SERVER_NAME,
                    "version": settings.SERVER_VERSION,
                },
                "instructions": settings.DOMAIN_KNOWLEDGE,
            },
        )

    def _handle_tools_list(self, request_id, params):
        return make_success(request_id, {"tools": self._tools.list_tools()})

    def _handle_tools_call(self, request_id, params):
        name = params.get("name")
        arguments = params.get("arguments") or {}
        try:
            text = self._tools.call_text(name, arguments)
            return make_success(
                request_id,
                {"content": [{"type": "text", "text": text}], "isError": False},
            )
        except Exception as exc:
            logger.exception("tool %s", name)
            return make_success(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
