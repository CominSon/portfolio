"""Реестр tools report-project-mcp v3."""

import json
import logging

from report_mcp_agent.src.tools.project_tools import (
    AddReportRevisionTool,
    FindReportProjectsTool,
    GetReportContextTool,
    GetReportStatusTool,
    HealthcheckReportTool,
    ListReportFilesTool,
    ReadReportFileTool,
    RefreshProjectDdlTool,
    RefreshProjectStructureTool,
    RemoveLineageObjectsTool,
    RenderReportDocsTool,
    ResolveReportRevisionTool,
    ResumeReportProjectTool,
    SetExtraKnowledgeTool,
    StartReportProjectTool,
    UpdateInventoryTool,
    UpsertLineageStepTool,
    UpsertScheduleEntryTool,
    ValidateReportProjectTool,
    WriteReportFileTool,
)

logger = logging.getLogger("report_mcp.tools")


class ToolRegistry(object):
    def __init__(self):
        tools = [
            HealthcheckReportTool(),
            StartReportProjectTool(),
            ResumeReportProjectTool(),
            FindReportProjectsTool(),
            GetReportStatusTool(),
            GetReportContextTool(),
            AddReportRevisionTool(),
            ResolveReportRevisionTool(),
            UpsertLineageStepTool(),
            UpsertScheduleEntryTool(),
            RemoveLineageObjectsTool(),
            UpdateInventoryTool(),
            SetExtraKnowledgeTool(),
            WriteReportFileTool(),
            ReadReportFileTool(),
            ListReportFilesTool(),
            RenderReportDocsTool(),
            ValidateReportProjectTool(),
            RefreshProjectStructureTool(),
            RefreshProjectDdlTool(),
        ]
        self._tools = {t.name: t for t in tools}

    def list_tools(self):
        return [t.schema() for t in self._tools.values()]

    def call(self, name, arguments):
        tool = self._tools.get(name)
        if tool is None:
            raise ValueError("Неизвестный tool: {0}".format(name))
        logger.info("Вызов tool: %s", name)
        result = tool.execute(arguments or {})
        if isinstance(result, (dict, list)):
            return result
        return {"result": result}

    def call_text(self, name, arguments):
        result = self.call(name, arguments)
        return json.dumps(result, ensure_ascii=False, indent=2)
