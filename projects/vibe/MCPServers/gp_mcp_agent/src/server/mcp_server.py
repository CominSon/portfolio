"""MCP-сервер Greenplum: JSON-RPC lifecycle и маршрутизация tools."""

import logging
from enum import Enum

from typing import Any, Dict, Optional

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.server.mcp_protocol import (
    StdioTransport,
    make_error,
    make_success,
)
from gp_mcp_agent.src.db.db_manager import DatabaseError
from gp_mcp_agent.src.server.tool_registry import ToolRegistry
from gp_mcp_agent.src.utils.tool_errors import short_db_message

logger = logging.getLogger("gp_mcp.server")


class ServerState(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    READY = "ready"


class MCPServer(object):
    def __init__(self, transport=None):
        # type: (Optional[StdioTransport]) -> None
        self._transport = transport or StdioTransport()
        self._tools = ToolRegistry()
        self._state = ServerState.UNINITIALIZED
        self._negotiated_version = settings.DEFAULT_PROTOCOL_VERSION

    def run(self):
        logger.info(
            "MCP-сервер запущен (%s v%s)",
            settings.SERVER_NAME,
            settings.SERVER_VERSION,
        )
        try:
            while True:
                try:
                    message = self._transport.read_message()
                except (ValueError, EOFError) as exc:
                    logger.warning("Пропуск битого MCP-сообщения: %s", exc)
                    continue
                if message is None:
                    logger.info("stdin закрыт, завершение работы")
                    break
                self._process_message(message)
        except KeyboardInterrupt:
            logger.info("Получен SIGINT, завершение")
        except Exception:
            logger.exception("Критическая ошибка сервера")
        finally:
            logger.info("MCP-сервер остановлен")

    def _process_message(self, message):
        # type: (Dict[str, Any]) -> None
        method = message.get("method")
        request_id = message.get("id")
        is_notification = "id" not in message and method is not None

        try:
            response = self._dispatch(message)
        except Exception as exc:
            logger.exception("Ошибка обработки %s", method)
            if is_notification:
                return
            response = make_error(request_id, str(exc))

        if response is None:
            return

        if is_notification:
            return

        self._transport.write_message(response)

    def _dispatch(self, message):
        # type: (Dict[str, Any]) -> Optional[Dict[str, Any]]
        method = message.get("method")
        request_id = message.get("id")
        params = message.get("params") or {}

        if method in ("notifications/initialized", "initialized"):
            self._state = ServerState.READY
            logger.info("Клиент отправил initialized, сервер готов к работе")
            return None

        if method == "notifications/cancelled":
            logger.debug("Получено notifications/cancelled")
            return None

        if request_id is None and method:
            logger.warning("Неизвестное уведомление: %s", method)
            return None

        if method == "initialize":
            return self._handle_initialize(request_id, params)

        if self._state == ServerState.UNINITIALIZED:
            return make_error(
                request_id,
                "Сервер не инициализирован. Сначала вызовите initialize.",
                code=-32002,
            )

        handlers = {
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "resources/list": self._handle_resources_list,
            "prompts/list": self._handle_prompts_list,
        }

        handler = handlers.get(method)
        if handler is None:
            logger.warning("Неизвестный метод: %s", method)
            return make_error(
                request_id,
                "Метод не поддерживается: {0}".format(method),
                code=-32601,
            )

        return handler(request_id, params)

    def _handle_initialize(self, request_id, params):
        # type: (Any, dict) -> Dict[str, Any]
        client_version = params.get(
            "protocolVersion", settings.DEFAULT_PROTOCOL_VERSION
        )
        self._negotiated_version = self._negotiate_version(client_version)
        self._state = ServerState.INITIALIZED

        client_info = params.get("clientInfo", {})
        logger.info(
            "initialize: client=%s %s, protocol=%s -> %s",
            client_info.get("name", "?"),
            client_info.get("version", "?"),
            client_version,
            self._negotiated_version,
        )

        return make_success(request_id, {
            "protocolVersion": self._negotiated_version,
            "capabilities": {
                "tools": {"listChanged": False},
            },
            "serverInfo": {
                "name": settings.SERVER_NAME,
                "version": settings.SERVER_VERSION,
            },
            "instructions": (
                "MCP-сервер Greenplum. Только SELECT/WITH/EXPLAIN. "
                "Схемы: {0}. "
                "Имена объектов: schema.table (qualified) или schema + name. "
                "DDL таблицы: get_table_ddl; DDL функции: get_function (owner в full_ddl). "
                "Владение объектами профиля: list_owned_objects (не run_select по pg_namespace). "
                "Мои сессии / активные запросы: list_sessions(scope=self), не run_select по pg_stat_activity. "
                "При isError=true и retry_recommended — исправь SQL и повтори tool (до 3 попыток). "
                "JSON в GP: -> / ->>, не @?. "
                "Большие выборки: export_query_csv или export_csv=true → CSV в gp_mcp_exports (cwd проекта). "
                "{1}"
            ).format(
                ", ".join(settings.GP_ALLOWED_SCHEMAS),
                settings.DOMAIN_KNOWLEDGE.strip(),
            ),
        })

    @staticmethod
    def _negotiate_version(client_version):
        # type: (str) -> str
        if client_version in settings.SUPPORTED_PROTOCOL_VERSIONS:
            return client_version
        return settings.DEFAULT_PROTOCOL_VERSION

    @staticmethod
    def _handle_ping(request_id, _params):
        return make_success(request_id, {})

    def _handle_tools_list(self, request_id, _params):
        return make_success(request_id, {"tools": self._tools.list_schemas()})

    def _handle_tools_call(self, request_id, params):
        from gp_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments

        tool_name = params.get("name")
        arguments = normalize_tool_arguments(params.get("arguments"))

        if not tool_name:
            return make_error(request_id, "Не указано имя tool", code=-32602)

        try:
            result = self._tools.call(tool_name, arguments)
            return make_success(request_id, result)
        except KeyError as exc:
            return make_error(request_id, str(exc), code=-32602)
        except ValueError as exc:
            logger.warning("Ошибка параметров tool %s: %s", tool_name, exc)
            err = self._tools.call_error(
                tool_name,
                str(exc),
                error_type="ValidationError",
                hint="Проверьте параметры tool или используйте qualified schema.object.",
            )
            logger.info("Отправлен ответ isError=true для tool %s (validation)", tool_name)
            return make_success(request_id, err)
        except DatabaseError as exc:
            from gp_mcp_agent.src.utils.db_error_hints import analyze_db_error

            short = short_db_message(exc)
            retry_meta = analyze_db_error(tool_name, exc)
            err = self._tools.call_error(
                tool_name,
                short,
                error_type="DatabaseError",
                hint=retry_meta.get("hint"),
                detail=str(exc),
                retry_meta=retry_meta,
            )
            logger.info(
                "Отправлен ответ isError=true для tool %s (db): %s",
                tool_name,
                short,
            )
            return make_success(request_id, err)
        except Exception as exc:
            logger.exception("Неожиданная ошибка tool %s", tool_name)
            err = self._tools.call_error(
                tool_name,
                short_db_message(exc),
                error_type=type(exc).__name__,
                detail=str(exc),
            )
            logger.info("Отправлен ответ isError=true для tool %s (unexpected)", tool_name)
            return make_success(request_id, err)

    @staticmethod
    def _handle_resources_list(request_id, _params):
        return make_success(request_id, {"resources": []})

    @staticmethod
    def _handle_prompts_list(request_id, _params):
        return make_success(request_id, {"prompts": []})
