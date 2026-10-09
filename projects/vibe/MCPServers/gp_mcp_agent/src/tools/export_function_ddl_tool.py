"""Запись DDL функции из Greenplum напрямую в файл (минуя LLM)."""

from pathlib import Path

from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.tools.get_function_tool import GetFunctionTool, _build_full_ddl
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from mcp_workspace_config.text_normalize import ddl_looks_corrupted, normalize_file_content


class ExportFunctionDdlTool(BaseTool):
    name = "export_function_ddl"
    description = (
        "Полный DDL функции из pg_get_functiondef → файл на диск. "
        "Не передавать тело через LLM/write_report_file.content."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string"},
                "schema": {"type": "string"},
                "name": {"type": "string"},
                "output_path": {
                    "type": "string",
                    "description": "Абсолютный путь к .sql",
                },
                "report_project_root": {"type": "string"},
                "relative_path": {
                    "type": "string",
                    "description": "Напр. sql/ddl/functions/schema.proc.sql",
                },
            },
        }

    def execute(self, arguments):
        schema, name = resolve_schema_name(arguments)
        result = GetFunctionTool().execute({
            "schema": schema,
            "name": name,
            "for_lineage": False,
        })
        if not result.get("full_ddl") and not result.get("exists", True):
            return result

        ddl = result.get("full_ddl") or ""
        if ddl_looks_corrupted(ddl):
            return {
                "ok": False,
                "error": "DDL из БД выглядит повреждённым — проверьте pg_get_functiondef",
            }

        output_path = (arguments.get("output_path") or "").strip()
        if not output_path:
            root = (arguments.get("report_project_root") or "").strip()
            rel = (arguments.get("relative_path") or "").strip()
            if not rel:
                rel = "sql/ddl/functions/{0}.{1}.sql".format(schema, name)
            if not root:
                raise ValueError("Укажите output_path или report_project_root + relative_path")
            output_path = str(Path(root) / rel)

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rel_name = path.name
        body = normalize_file_content(ddl, rel_name)
        path.write_text(body, encoding="utf-8")

        return {
            "ok": True,
            "path": str(path),
            "bytes": len(body.encode("utf-8")),
            "procedure": "{0}.{1}".format(schema, name),
            "hint": "DDL записан из БД. Для lineage: get_function(writes_to=…) отдельно.",
        }
