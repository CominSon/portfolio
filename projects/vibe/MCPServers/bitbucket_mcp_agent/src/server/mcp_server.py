import logging
from enum import Enum

from bitbucket_mcp_agent.resources import settings
from bitbucket_mcp_agent.src.server.mcp_protocol import StdioTransport, make_error, make_success
from bitbucket_mcp_agent.src.server.tool_registry import ToolRegistry

logger = logging.getLogger("bb_mcp.server")


class ServerState(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    READY = "ready"


class MCPServer(object):
    def __init__(self, transport=None):
        self._transport = transport or StdioTransport()
        self._tools = ToolRegistry()
        self._state = ServerState.UNINITIALIZED

    def run(self):
        logger.info("Старт %s v%s", settings.SERVER_NAME, settings.SERVER_VERSION)
        try:
            while True:
                try:
                    msg = self._transport.read_message()
                except (ValueError, EOFError) as exc:
                    logger.warning("Пропуск битого MCP-сообщения: %s", exc)
                    continue
                if msg is None:
                    break
                self._process(msg)
        finally:
            logger.info("Остановка")

    def _process(self, message):
        method = message.get("method")
        request_id = message.get("id")
        is_notification = "id" not in message and method
        try:
            response = self._dispatch(message)
        except Exception as exc:
            logger.exception("Ошибка")
            if is_notification:
                return
            response = make_error(request_id, str(exc))
        if response and not is_notification:
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
            self._state = ServerState.INITIALIZED
            ver = params.get("protocolVersion", settings.DEFAULT_PROTOCOL_VERSION)
            if ver not in settings.SUPPORTED_PROTOCOL_VERSIONS:
                ver = settings.DEFAULT_PROTOCOL_VERSION
            return make_success(request_id, {
                "protocolVersion": ver,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": settings.SERVER_NAME,
                    "version": settings.SERVER_VERSION,
                },
                "instructions": (
                    "MCP Git/Bitbucket WEALTHHUB. "
                    "get_project_path / set_project_path при смене репо в IDEA. "
                    "Коммит+push: один вызов commit_and_push (dot-файлы исключены автоматически). "
                    "Чтение (git_status, git_diff, git_compare_recent, git_log) — сразу, без «можно?». "
                    "Не используйте prepare_commit/prepare_push — они удалены. "
                    "{0}"
                ).format(settings.DOMAIN_KNOWLEDGE.strip()),
            })
        if self._state == ServerState.UNINITIALIZED:
            return make_error(request_id, "Сначала initialize.", code=-32002)

        handlers = {
            "ping": lambda rid, p: make_success(rid, {}),
            "tools/list": lambda rid, p: make_success(rid, {"tools": self._tools.list_schemas()}),
            "tools/call": self._handle_call,
            "resources/list": lambda rid, p: make_success(rid, {"resources": []}),
            "prompts/list": lambda rid, p: make_success(rid, {"prompts": []}),
        }
        h = handlers.get(method)
        if not h:
            return make_error(request_id, "Не поддерживается: {0}".format(method), code=-32601)
        return h(request_id, params)

    def _handle_call(self, request_id, params):
        from bitbucket_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments

        name = params.get("name")
        args = normalize_tool_arguments(params.get("arguments"))
        if not name:
            return make_error(request_id, "Нет имени tool", code=-32602)
        try:
            return make_success(request_id, self._tools.call(name, args))
        except KeyError as exc:
            return make_error(request_id, str(exc), code=-32602)
        except ValueError as exc:
            return make_success(
                request_id,
                self._tools.call_error(name, str(exc), error_type="ValidationError"),
            )
        except Exception as exc:
            logger.exception("tool %s", name)
            return make_success(
                request_id,
                self._tools.call_error(name, str(exc), error_type=type(exc).__name__),
            )
