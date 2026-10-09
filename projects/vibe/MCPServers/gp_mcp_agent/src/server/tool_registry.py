"""Реестр MCP tools."""

import json
import logging

from typing import Any, Callable, Dict, List

from gp_mcp_agent.src.tools.get_object_info_tool import GetObjectInfoTool
from gp_mcp_agent.src.tools.get_procedure_schedule_tool import GetProcedureScheduleTool
from gp_mcp_agent.src.tools.get_view_ddl_tool import GetViewDdlTool
from gp_mcp_agent.src.tools.verify_object_terminal_tool import VerifyObjectTerminalTool
from gp_mcp_agent.src.tools.build_full_lineage_tool import BuildFullLineageTool
from gp_mcp_agent.src.tools.compare_field_values_tool import CompareFieldValuesTool
from gp_mcp_agent.src.tools.compare_tables_tool import CompareTablesTool
from gp_mcp_agent.src.tools.export_query_csv_tool import ExportQueryCsvTool
from gp_mcp_agent.src.tools.explain_tool import ExplainTool
from gp_mcp_agent.src.tools.find_blocking_tool import FindBlockingTool
from gp_mcp_agent.src.tools.export_function_ddl_tool import ExportFunctionDdlTool
from gp_mcp_agent.src.tools.export_view_ddl_tool import ExportViewDdlTool
from gp_mcp_agent.src.tools.find_functions_for_table_tool import FindFunctionsForTableTool
from gp_mcp_agent.src.tools.get_columns_tool import GetColumnsTool
from gp_mcp_agent.src.tools.get_function_tool import GetFunctionTool
from gp_mcp_agent.src.tools.get_link_object_tool import GetLinkObjectTool
from gp_mcp_agent.src.tools.get_table_ddl_tool import GetTableDdlTool
from gp_mcp_agent.src.tools.healthcheck_tool import HealthcheckTool
from gp_mcp_agent.src.tools.list_owned_objects_tool import ListOwnedObjectsTool
from gp_mcp_agent.src.tools.load_file_to_table_tool import LoadFileToTableTool
from gp_mcp_agent.src.tools.project_path_tools import (
    GetProjectPathTool,
    SetProjectPathTool,
    UseMcpCwdAsProjectTool,
)
from gp_mcp_agent.src.tools.list_sessions_tool import ListSessionsTool
from gp_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments
from gp_mcp_agent.src.utils.tool_errors import build_tool_error_payload
from gp_mcp_agent.src.tools.run_select_tool import RunSelectTool
from gp_mcp_agent.src.tools.search_tables_tool import SearchTablesTool

logger = logging.getLogger("gp_mcp.tools")


class ToolRegistry(object):
    def __init__(self):
        self._tools = {
            "healthcheck": HealthcheckTool(),
            "run_select": RunSelectTool(),
            "export_query_csv": ExportQueryCsvTool(),
            "explain": ExplainTool(),
            "search_tables": SearchTablesTool(),
            "get_columns": GetColumnsTool(),
            "get_table_ddl": GetTableDdlTool(),
            "get_view_ddl": GetViewDdlTool(),
            "get_object_info": GetObjectInfoTool(),
            "get_function": GetFunctionTool(),
            "export_function_ddl": ExportFunctionDdlTool(),
            "export_view_ddl": ExportViewDdlTool(),
            "compare_tables": CompareTablesTool(),
            "list_sessions": ListSessionsTool(),
            "find_blocking": FindBlockingTool(),
            "find_functions_for_table": FindFunctionsForTableTool(),
            "get_link_object": GetLinkObjectTool(),
            "verify_object_terminal": VerifyObjectTerminalTool(),
            "compare_field_values": CompareFieldValuesTool(),
            "build_full_lineage": BuildFullLineageTool(),
            "get_procedure_schedule": GetProcedureScheduleTool(),
            "list_owned_objects": ListOwnedObjectsTool(),
            "get_project_path": GetProjectPathTool(),
            "set_project_path": SetProjectPathTool(),
            "use_mcp_cwd_as_project": UseMcpCwdAsProjectTool(),
            "load_file_to_table": LoadFileToTableTool(),
        }

    def list_schemas(self):
        # type: () -> List[dict]
        return [tool.schema() for tool in self._tools.values()]

    def call(self, name, arguments):
        # type: (str, Dict[str, Any]) -> Dict[str, Any]
        arguments = normalize_tool_arguments(arguments)
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError("Неизвестный tool: {0}".format(name))

        logger.info("Вызов tool: %s, args=%s", name, list(arguments.keys()))
        result = tool.execute(arguments)
        skip_compact = bool(arguments.get("skip_spill") or arguments.get("skip_compact"))
        try:
            from mcp_workspace_config.active_report_project import get_active_report_project
            from mcp_workspace_config.agent_session_store import gp_should_spill, spill_tool_result

            if arguments.get("skip_spill"):
                spill_root = None
            else:
                active = get_active_report_project() or {}
                spill_root = (arguments or {}).get("report_project_root") or active.get("project_root")
            if spill_root:
                try:
                    from report_mcp_agent.src.report.manifest import load_manifest

                    if not load_manifest(spill_root):
                        spill_root = None
                except Exception:
                    spill_root = None
            if spill_root and gp_should_spill(name):
                result = spill_tool_result(
                    spill_root, name, arguments, result, mcp_server="gp-greenplum"
                )
        except Exception as exc:
            logger.warning("gp registry spill skip: %s", exc, exc_info=True)
        try:
            if skip_compact:
                text = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
            else:
                from mcp_workspace_config.response_compact import compact_tool_result, dumps_compact
                result = compact_tool_result(name, result, server="gp")
                text = dumps_compact(result)
        except Exception:
            text = json.dumps(result, ensure_ascii=False, default=str, separators=(",", ":"))
        return {
            "content": [{"type": "text", "text": text}],
        }

    def call_error(self, tool_name, message, error_type=None, hint=None, detail=None, retry_meta=None):
        # type: (str, str, Any, Any, Any, Any) -> Dict[str, Any]
        payload = build_tool_error_payload(
            tool_name,
            message,
            error_type=error_type,
            hint=hint,
            detail=detail,
            retry_meta=retry_meta,
        )
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        return {
            "content": [{"type": "text", "text": text}],
            "isError": True,
        }
