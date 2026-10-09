from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools._external_ddl import _fetch_gp_external_ddl
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name


def _is_external_table(schema, table):
    rows = db_manager.fetch_all(
        """
        SELECT 1
        FROM pg_catalog.pg_exttable e
        JOIN pg_catalog.pg_class c ON e.reloid = c.oid
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = :schema
          AND c.relname = :table
        LIMIT 1
        """,
        {"schema": schema, "table": table},
    )
    return bool(rows)


def _build_create_table_ddl(schema, table, columns, is_external, owner, external_options=None):
    keyword = "CREATE EXTERNAL TABLE" if is_external else "CREATE TABLE"
    lines = ["{0} {1}.{2} (".format(keyword, schema, table)]

    col_lines = []
    for col in columns:
        nullable = "" if (col.get("is_nullable") or "").upper() == "YES" else " NOT NULL"
        col_lines.append(
            "    {0} {1}{2}".format(
                col["column_name"],
                col["data_type"],
                nullable,
            )
        )
    lines.append(",\n".join(col_lines))
    lines.append(")")
    if external_options:
        lines.append(external_options)
    lines.append(";")

    ddl = "\n".join(lines)
    if owner:
        ddl += "\n\nALTER TABLE {0}.{1} OWNER TO {2};".format(schema, table, owner)
    return ddl


class GetTableDdlTool(BaseTool):
    name = "get_table_ddl"
    description = (
        "DDL таблицы (CREATE TABLE / CREATE EXTERNAL TABLE) с LOCATION/FORMAT для external. "
        "Можно передать qualified: schema.table."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {
                    "type": "string",
                    "description": "Полное имя schema.table",
                },
                "schema": {"type": "string"},
                "table": {"type": "string"},
            },
        }

    def execute(self, arguments):
        schema, table = resolve_schema_name(arguments, name_key="table")
        db_manager.validate_schema(schema)

        meta = db_manager.fetch_all(
            """
            SELECT
                c.relkind,
                pg_catalog.pg_get_userbyid(c.relowner) AS owner,
                COALESCE(
                    pg_catalog.pg_get_userbyid(c.relowner),
                    (SELECT r.rolname FROM pg_catalog.pg_roles r WHERE r.oid = c.relowner)
                ) AS owner_resolved
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = :schema
              AND c.relname = :table
            """,
            {"schema": schema, "table": table},
        )

        if not meta:
            return {
                "schema": schema,
                "table": table,
                "exists": False,
                "error": "Таблица не найдена в pg_catalog",
            }

        owner = meta[0].get("owner_resolved") or meta[0].get("owner")
        is_external = _is_external_table(schema, table)

        table_info = db_manager.fetch_all(
            """
            SELECT table_type
            FROM information_schema.tables
            WHERE table_schema = :schema AND table_name = :table
            """,
            {"schema": schema, "table": table},
        )
        table_type = table_info[0]["table_type"] if table_info else "BASE TABLE"
        if is_external:
            table_type = "EXTERNAL TABLE"

        columns = db_manager.fetch_all(
            """
            SELECT column_name, data_type, is_nullable, ordinal_position
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
            """,
            {"schema": schema, "table": table},
        )

        external_clause = None
        if is_external:
            external_clause = _fetch_gp_external_ddl(schema, table)

        full_ddl = _build_create_table_ddl(
            schema, table, columns, is_external, owner, external_clause
        )

        return {
            "schema": schema,
            "table": table,
            "exists": True,
            "is_external": is_external,
            "table_type": table_type,
            "owner": owner,
            "column_count": len(columns),
            "columns": columns,
            "external_options": external_clause,
            "full_ddl": full_ddl,
            "note": (
                "External определяется по pg_exttable (не information_schema). "
                "LOCATION/FORMAT/ENCODING в full_ddl."
            ),
        }
