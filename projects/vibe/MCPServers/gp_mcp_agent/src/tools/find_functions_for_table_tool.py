from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.gp_function_search import (
    search_functions_for_table,
    search_views_for_table,
)
from gp_mcp_agent.src.utils.link_object_search import (
    discover_writers_via_link_object,
    merge_writer_lists,
)
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from gp_mcp_agent.src.utils.write_classifier import (
    branch_role_for_target,
    classify_write_to_table,
    rank_writers,
    resolve_exclude_suffixes,
    write_roles_summary,
)


def _fetch_full_body(schema, function_name):
    rows = db_manager.fetch_all(
        """
        SELECT left(p.prosrc, 12000) AS definition
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = :schema AND p.proname = :name
        ORDER BY p.oid LIMIT 1
        """,
        {"schema": schema, "name": function_name},
    )
    return (rows[0].get("definition") or "") if rows else ""


class FindFunctionsForTableTool(BaseTool):
    name = "find_functions_for_table"
    description = (
        "Кто использует/наполняет ОДНУ таблицу. writers — все процедуры с DML. "
        "Для КАЖДОГО primary writer — отдельный шаг цепочки."
    )

    def input_schema(self):
        return {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "qualified": {
                    "type": "string",
                    "description": "schema.table, напр. work.qs_t_ukp_weeks",
                },
                "schema": {
                    "type": "string",
                    "description": "work | in | ext или полное имя схемы",
                },
                "table": {"type": "string", "description": "Имя таблицы"},
                "search_mode": {
                    "type": "string",
                    "enum": ["qualified", "table_only", "both"],
                },
                "exclude_name_suffixes": {"type": "array", "items": {"type": "string"}},
                "exclude_dtl": {"type": "boolean"},
                "report_project_root": {
                    "type": "string",
                    "description": "Папка проекта отчёта — spill на диск",
                },
            },
        }

    def execute(self, arguments):
        schema, table = resolve_schema_name(arguments, name_key="table")
        db_manager.validate_schema(schema)

        mode = (arguments.get("search_mode") or "both").strip().lower()
        suffixes = resolve_exclude_suffixes(
            arguments.get("exclude_name_suffixes"),
            bool(arguments.get("exclude_dtl")),
        )

        import logging
        _log = logging.getLogger("gp_mcp.tools.find_functions")
        _log.info("find_functions start %s.%s mode=%s", schema, table, mode)
        functions, _ = search_functions_for_table(
            schema, table, mode, exclude_name_suffixes=suffixes or None
        )
        _log.info("find_functions catalog candidates=%s", len(functions or []))
        views = search_views_for_table(schema, table)

        writers = []
        discovery_sources = []
        for row in functions:
            preview = row.get("definition") or ""
            body = preview
            if len(preview) >= 3900:
                body = _fetch_full_body(row.get("schema_name"), row.get("function_name")) or preview

            roles = classify_write_to_table(body, schema, table)
            if not roles:
                continue

            writers.append({
                "qualified": "{0}.{1}".format(row.get("schema_name"), row.get("function_name")),
                "write_roles": roles,
                "write_role": write_roles_summary(roles),
                "branch_role": branch_role_for_target(roles),
                "discovery": "catalog",
            })
        if writers:
            discovery_sources.append("catalog")

        # Всегда дополняем через f_get_link_object — каталог/ILIKE часто неполные
        link_writers = discover_writers_via_link_object(
            schema, table, exclude_name_suffixes=suffixes or None, limit=0
        )
        if link_writers:
            discovery_sources.append("link_object")
            writers = merge_writer_lists(writers, link_writers)

        writers = rank_writers(writers)
        primary = [w["qualified"] for w in writers if w.get("branch_role") == "primary"]
        supplement = [w["qualified"] for w in writers if w.get("branch_role") == "supplement"]
        target = "{0}.{1}".format(schema, table)
        writer_names = [w["qualified"] for w in writers]

        return {
            "target": target,
            "writers": writers,
            "writer_count": len(writers),
            "writer_names": writer_names,
            "primary_writers": primary,
            "supplement_writers": supplement,
            "views": views,
            "discovery_sources": discovery_sources,
            "lineage_probe": {
                "gp_tool": "find_functions_for_table",
                "target_object": target,
                "primary_writers": primary,
                "supplement_writers": supplement,
            },
            "next_actions": [
                "Lineage для проекта отчёта: агент сам через GP + report upsert_lineage_step "
                "(нет build_report_project).",
            ],
        }
