from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from gp_mcp_agent.src.utils.sql_table_refs import extract_table_refs, format_table_refs
from mcp_workspace_config.text_normalize import normalize_line_endings


class GetViewDdlTool(BaseTool):
    name = "get_view_ddl"
    description = (
        "DDL представления (CREATE VIEW) + tables_referenced из тела view "
        "(включая prx_* / внешние схемы). Для записи на диск — export_view_ddl."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string"},
                "schema": {"type": "string"},
                "view": {"type": "string", "description": "Имя view / matview"},
            },
        }

    def execute(self, arguments):
        schema, view = resolve_schema_name(arguments, name_key="view")
        db_manager.validate_schema(schema)

        meta = db_manager.fetch_all(
            """
            SELECT c.relkind,
                   pg_catalog.pg_get_userbyid(c.relowner) AS owner,
                   COALESCE(
                       pg_catalog.pg_get_userbyid(c.relowner),
                       (SELECT r.rolname FROM pg_catalog.pg_roles r WHERE r.oid = c.relowner)
                   ) AS owner_resolved
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema AND c.relname = :view
            """,
            {"schema": schema, "view": view},
        )
        if not meta:
            return {"schema": schema, "view": view, "exists": False}

        relkind = meta[0].get("relkind")
        owner = meta[0].get("owner_resolved") or meta[0].get("owner")

        if relkind == "m":
            rows = db_manager.fetch_all(
                """
                SELECT definition
                FROM pg_catalog.pg_matviews
                WHERE schemaname = :schema AND matviewname = :view
                """,
                {"schema": schema, "view": view},
            )
            object_kind = "materialized_view"
            keyword = "CREATE MATERIALIZED VIEW"
        else:
            rows = db_manager.fetch_all(
                """
                SELECT definition
                FROM pg_catalog.pg_views
                WHERE schemaname = :schema AND viewname = :view
                """,
                {"schema": schema, "view": view},
            )
            object_kind = "view"
            keyword = "CREATE VIEW"

        if not rows or not rows[0].get("definition"):
            return {
                "schema": schema,
                "view": view,
                "exists": True,
                "object_kind": object_kind,
                "error": "Не удалось получить definition",
            }

        body = normalize_line_endings(rows[0]["definition"])
        full_ddl = "{0} {1}.{2} AS\n{3}".format(keyword, schema, view, body)
        if owner:
            full_ddl += "\n\nALTER VIEW {0}.{1} OWNER TO {2};".format(schema, view, owner)

        refs = extract_table_refs(body, include_all_schemas=True)
        tables_referenced = format_table_refs(refs)
        upstream = [r["qualified"] for r in tables_referenced]

        return {
            "schema": schema,
            "view": view,
            "exists": True,
            "object_kind": object_kind,
            "owner": owner,
            "definition": body,
            "full_ddl": full_ddl,
            "tables_referenced": tables_referenced,
            "upstream_sources": upstream,
            "terminal_candidates": [
                r["qualified"] for r in tables_referenced if r.get("is_external")
            ],
            "note": (
                "Источники view — upstream_sources / tables_referenced. "
                "prx_* — терминал PXF, verify_object_terminal + register в terminal_sources."
            ),
            "hint": (
                "DDL на диск: export_view_ddl(output_path=...). "
                "Не get_session_artifact + write_report_file."
            ),
        }
