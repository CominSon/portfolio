"""Запись DDL view/matview из Greenplum напрямую в файл."""

from pathlib import Path

from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.tools.get_view_ddl_tool import GetViewDdlTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from mcp_workspace_config.text_normalize import ddl_looks_corrupted, normalize_file_content


class ExportViewDdlTool(BaseTool):
    name = "export_view_ddl"
    description = (
        "Полный DDL view из pg_views → файл на диск. "
        "Аналог export_function_ddl для представлений."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string"},
                "schema": {"type": "string"},
                "view": {"type": "string"},
                "output_path": {"type": "string"},
                "report_project_root": {"type": "string"},
                "relative_path": {
                    "type": "string",
                    "description": "Напр. sql/ddl/objects/schema.view.sql",
                },
            },
        }

    def execute(self, arguments):
        schema, view = resolve_schema_name(arguments, name_key="view")
        result = GetViewDdlTool().execute({
            "schema": schema,
            "view": view,
        })
        if not result.get("exists"):
            return result

        ddl = result.get("full_ddl") or ""
        if ddl_looks_corrupted(ddl):
            return {"ok": False, "error": "DDL view повреждён — проверьте pg_views"}

        output_path = (arguments.get("output_path") or "").strip()
        if not output_path:
            root = (arguments.get("report_project_root") or "").strip()
            rel = (arguments.get("relative_path") or "").strip()
            if not rel:
                rel = "sql/ddl/objects/{0}.{1}.sql".format(schema, view)
            if not root:
                raise ValueError("Укажите output_path или report_project_root + relative_path")
            output_path = str(Path(root) / rel)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = normalize_file_content(ddl, path.name)
        path.write_text(body, encoding="utf-8")

        return {
            "ok": True,
            "path": str(path),
            "bytes": len(body.encode("utf-8")),
            "view": "{0}.{1}".format(schema, view),
            "upstream_sources": result.get("upstream_sources"),
            "terminal_candidates": result.get("terminal_candidates"),
            "hint": "verify_object_terminal для terminal_candidates; view не register_lineage_step как procedure.",
        }
