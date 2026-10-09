from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from gp_mcp_agent.src.utils.sql_block_extractor import analyze_procedure_for_target
from gp_mcp_agent.src.utils.write_classifier import (
    branch_role_for_target,
    classify_write_to_table,
    write_roles_summary,
)
from mcp_workspace_config.text_normalize import normalize_line_endings


def _build_full_ddl(row):
    definition = normalize_line_endings((row.get("definition") or "").strip())
    owner = row.get("owner")
    schema = row.get("schema_name")
    name = row.get("function_name")
    args = row.get("arguments") or ""
    if owner and schema and name:
        alter = "ALTER FUNCTION {0}.{1}({2}) OWNER TO {3};".format(schema, name, args, owner)
        if alter.strip() not in definition:
            definition = definition + "\n\n" + alter
    return definition


class GetFunctionTool(BaseTool):
    name = "get_function"
    description = (
        "DDL процедуры. Для анализа lineage: writes_to=schema.table → reads_from_for_lineage. "
        "Без writes_to — только экспорт DDL (не для определения источников)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string"},
                "schema": {"type": "string"},
                "name": {"type": "string"},
                "writes_to": {
                    "type": "string",
                    "description": "schema.table — для анализа источников (lineage)",
                },
                "for_lineage": {
                    "type": "boolean",
                    "description": "true = требовать writes_to, не отдавать tables_referenced всей функции",
                },
                "include_ddl": {
                    "type": "boolean",
                    "description": "true = включить full_ddl в ответ (для export). "
                    "По умолчанию false при for_lineage — иначе MCP зависает на spill крупных процедур.",
                },
                "report_project_root": {
                    "type": "string",
                    "description": "Папка проекта отчёта — полный ответ пишется на диск, в чат кратко",
                },
                "skip_spill": {
                    "type": "boolean",
                    "description": "true = не писать artifact (вызов из orchestrator)",
                },
            },
        }

    def execute(self, arguments):
        schema, name = resolve_schema_name(arguments)
        db_manager.validate_schema(schema)

        writes_to = (arguments.get("writes_to") or "").strip()
        for_lineage = arguments.get("for_lineage")
        if for_lineage is None:
            for_lineage = bool(writes_to)
        include_ddl = arguments.get("include_ddl")
        if include_ddl is None:
            include_ddl = not for_lineage

        if for_lineage and (not writes_to or "." not in writes_to):
            raise ValueError("Для lineage укажите writes_to=schema.table")

        functions = db_manager.fetch_all(
            """
            SELECT
                n.nspname AS schema_name,
                p.proname AS function_name,
                pg_get_function_identity_arguments(p.oid) AS arguments,
                pg_catalog.pg_get_userbyid(p.proowner) AS owner,
                pg_get_functiondef(p.oid) AS definition
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = :schema AND p.proname = :name
            ORDER BY p.oid
            """,
            {"schema": schema, "name": name},
        )

        if not functions:
            return {"exists": False, "schema": schema, "name": name}

        row = functions[0]
        body = row.get("definition") or ""
        full_ddl = _build_full_ddl(row) if include_ddl else None

        if not for_lineage:
            return {
                "schema": schema,
                "name": name,
                "owner": row.get("owner"),
                "full_ddl": full_ddl or _build_full_ddl(row),
                "mode": "ddl_export",
            }

        target_schema, target_table = writes_to.split(".", 1)
        db_manager.validate_schema(target_schema)
        roles = classify_write_to_table(body, target_schema, target_table)
        analysis = analyze_procedure_for_target(body, target_schema, target_table)
        reads = analysis.get("reads_from") or []
        data_reads = analysis.get("data_reads_from") or analysis.get("suggested_reads_from") or []
        reference_reads = analysis.get("reference_reads_from") or []
        if not data_reads:
            data_reads = [
                r.get("qualified") for r in reads if r.get("qualified")
            ]
            from gp_mcp_agent.src.utils.read_classifier import partition_reads
            data_reads, reference_reads = partition_reads(data_reads)

        result = {
            "mode": "lineage",
            "procedure": "{0}.{1}".format(schema, name),
            "writes_to": writes_to,
            "write_roles": roles,
            "write_role": write_roles_summary(roles),
            "branch_role": branch_role_for_target(roles),
            "suggested_reads_from": data_reads,
            "immediate_reads_from": data_reads,
            "data_reads_from": data_reads,
            "reference_reads_from": reference_reads,
            "join_reads_in_query": analysis.get("join_reads_in_query") or [],
            "cte_chain": analysis.get("cte_chain") or [],
            "union_branches": analysis.get("union_branches") or [],
            "temp_table_lineage": analysis.get("temp_table_lineage") or [],
            "reads_from_for_lineage": data_reads,
            "reads_from_count": len(data_reads),
            "heuristic_limitations": analysis.get("heuristic_limitations") or [],
            "llm_review_required": analysis.get("llm_review_required", True),
            "manual_review_required": analysis.get("manual_review_required"),
            "analysis_note": analysis.get("analysis_note"),
            "dml_block_previews": analysis.get("dml_block_previews"),
            "owner": row.get("owner"),
            "lineage_probe": {
                "gp_tool": "get_function",
                "procedure": "{0}.{1}".format(schema, name),
                "writes_to": writes_to,
                "reads_from_for_lineage": data_reads,
                "write_role": write_roles_summary(roles),
                "branch_role": branch_role_for_target(roles),
            },
        }
        if full_ddl:
            result["full_ddl"] = full_ddl

        if analysis.get("manual_review_required"):
            result["warning"] = (
                "Прочитайте union_branches и temp_table_lineage. "
                "reads_from = data_reads_from (ветки UNION + temp→physical). "
                "Вызовы f_* в SELECT не в reads_from. "
                "DDL в файл — export_function_ddl."
            )
        else:
            result["next_step_hint"] = (
                "1) data_reads_from → reads_from шага lineage. "
                "2) reference_reads_from → reference_reads (справочники). "
                "3) DDL → export_function_ddl."
            )
        return result
