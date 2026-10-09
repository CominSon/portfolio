from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool


class ListOwnedObjectsTool(BaseTool):
    name = "list_owned_objects"
    description = (
        "Объекты Greenplum по владельцу (rolname или oid): схемы, таблицы, "
        "представления, функции в разрешённых схемах. "
        "Для анализа владения профилем — используйте этот tool, "
        "не run_select по pg_catalog (в pg_namespace поле nspowner, не relowner)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "owner": {
                    "type": "string",
                    "description": "Имя роли (rolname) или числовой oid владельца",
                },
                "schema": {
                    "type": "string",
                    "description": "Ограничить одной схемой (из whitelist)",
                },
                "include_schemas": {
                    "type": "boolean",
                    "description": "Включить схемы (pg_namespace), default true",
                },
                "include_tables": {
                    "type": "boolean",
                    "description": "Таблицы и matviews (relkind r,m), default true",
                },
                "include_views": {
                    "type": "boolean",
                    "description": "Представления (relkind v), default true",
                },
                "include_functions": {
                    "type": "boolean",
                    "description": "Функции (pg_proc), default true",
                },
                "limit": {"type": "integer"},
            },
            "required": ["owner"],
        }

    def execute(self, arguments):
        owner_raw = (arguments.get("owner") or "").strip()
        if not owner_raw:
            raise ValueError("Параметр owner обязателен")

        schema_filter = (arguments.get("schema") or "").strip()
        if schema_filter:
            db_manager.validate_schema(schema_filter)
            schemas = [schema_filter]
        else:
            schemas = list(settings.GP_ALLOWED_SCHEMAS)

        include_schemas = arguments.get("include_schemas", True)
        include_tables = arguments.get("include_tables", True)
        include_views = arguments.get("include_views", True)
        include_functions = arguments.get("include_functions", True)
        limit = int(arguments.get("limit") or 200)
        limit = min(max(limit, 1), 500)

        owner_oid = None
        owner_name = owner_raw
        if owner_raw.isdigit():
            owner_oid = int(owner_raw)

        role_row = db_manager.fetch_all(
            """
            SELECT oid, rolname
            FROM pg_catalog.pg_roles
            WHERE rolname = :name OR oid = :oid
            LIMIT 1
            """,
            {"name": owner_raw, "oid": owner_oid or -1},
        )
        if not role_row:
            return {
                "ok": False,
                "error": True,
                "message": "Роль не найдена: {0}".format(owner_raw),
                "hint": "Проверьте rolname или oid в pg_roles.",
                "objects": [],
                "count": 0,
            }

        resolved_oid = role_row[0]["oid"]
        resolved_name = role_row[0]["rolname"]

        parts = []
        if include_schemas:
            parts.append(
                """
                SELECT 'schema' AS object_type,
                       n.nspname AS object_schema,
                       NULL::text AS object_name,
                       r.rolname AS owner
                FROM pg_catalog.pg_namespace n
                JOIN pg_catalog.pg_roles r ON r.oid = n.nspowner
                WHERE n.nspname = ANY(:schemas)
                  AND n.nspowner = :owner_oid
                """
            )

        if include_tables:
            parts.append(
                """
                SELECT 'table' AS object_type,
                       n.nspname AS object_schema,
                       c.relname AS object_name,
                       r.rolname AS owner
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
                WHERE n.nspname = ANY(:schemas)
                  AND c.relowner = :owner_oid
                  AND c.relkind IN ('r', 'm')
                """
            )

        if include_views:
            parts.append(
                """
                SELECT 'view' AS object_type,
                       n.nspname AS object_schema,
                       c.relname AS object_name,
                       r.rolname AS owner
                FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
                WHERE n.nspname = ANY(:schemas)
                  AND c.relowner = :owner_oid
                  AND c.relkind = 'v'
                """
            )

        if include_functions:
            parts.append(
                """
                SELECT 'function' AS object_type,
                       n.nspname AS object_schema,
                       p.proname AS object_name,
                       r.rolname AS owner
                FROM pg_catalog.pg_proc p
                JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
                JOIN pg_catalog.pg_roles r ON r.oid = p.proowner
                WHERE n.nspname = ANY(:schemas)
                  AND p.proowner = :owner_oid
                """
            )

        if not parts:
            raise ValueError("Нужно включить хотя бы один тип объектов")

        sql = (
            "SELECT * FROM ({0}) sub ORDER BY object_type, object_schema, object_name "
            "LIMIT :limit"
        ).format(" UNION ALL ".join(parts))

        rows = db_manager.fetch_all(
            sql,
            {
                "schemas": schemas,
                "owner_oid": resolved_oid,
                "limit": limit,
            },
        )

        return {
            "ok": True,
            "owner": resolved_name,
            "owner_oid": resolved_oid,
            "schemas_filter": schemas,
            "count": len(rows),
            "limit": limit,
            "objects": rows,
            "note": (
                "Схемы: pg_namespace.nspowner; таблицы/views: pg_class.relowner; "
                "функции: pg_proc.proowner."
            ),
        }
