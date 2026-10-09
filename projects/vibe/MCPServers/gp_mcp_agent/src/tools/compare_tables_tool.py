from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool


class CompareTablesTool(BaseTool):
    name = "compare_tables"
    description = (
        "Сравнить external table и материализованную таблицу "
        "{0}<table>.".format(settings.GP_MATERIALIZED_PREFIX)
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "description": "Имя external таблицы без префикса smd_",
                }
            },
            "required": ["table"],
        }

    def execute(self, arguments):
        table = arguments.get("table", "").strip()
        if not table:
            raise ValueError("Параметр 'table' обязателен")
        if table.startswith(settings.GP_MATERIALIZED_PREFIX):
            raise ValueError(
                "Укажите имя external-таблицы без префикса '{0}'".format(
                    settings.GP_MATERIALIZED_PREFIX
                )
            )

        ext_schema = settings.GP_EXTERNAL_SCHEMA
        mat_schema = settings.GP_MATERIALIZED_SCHEMA
        mat_table = "{0}{1}".format(settings.GP_MATERIALIZED_PREFIX, table)

        ext_exists = db_manager.table_exists(ext_schema, table)
        mat_exists = db_manager.table_exists(mat_schema, mat_table)

        ext_cols = self._get_columns(ext_schema, table) if ext_exists else []
        mat_cols = self._get_columns(mat_schema, mat_table) if mat_exists else []

        ext_map = dict((c["column_name"], c["data_type"]) for c in ext_cols)
        mat_map = dict((c["column_name"], c["data_type"]) for c in mat_cols)

        ext_names = set(ext_map.keys())
        mat_names = set(mat_map.keys())

        missing_in_materialized = sorted(ext_names - mat_names)
        extra_in_materialized = sorted(mat_names - ext_names)

        type_mismatches = []
        for col in sorted(ext_names & mat_names):
            if ext_map[col] != mat_map[col]:
                type_mismatches.append({
                    "column": col,
                    "external_type": ext_map[col],
                    "materialized_type": mat_map[col],
                })

        identical = (
            ext_exists
            and mat_exists
            and not missing_in_materialized
            and not extra_in_materialized
            and not type_mismatches
        )

        return {
            "external_table": "{0}.{1}".format(ext_schema, table),
            "materialized_table": "{0}.{1}".format(mat_schema, mat_table),
            "external_exists": ext_exists,
            "materialized_exists": mat_exists,
            "external_column_count": len(ext_cols),
            "materialized_column_count": len(mat_cols),
            "missing_in_materialized": [
                {"column": c, "type": ext_map[c]} for c in missing_in_materialized
            ],
            "extra_in_materialized": [
                {"column": c, "type": mat_map[c]} for c in extra_in_materialized
            ],
            "type_mismatches": type_mismatches,
            "identical": identical,
            "external_columns": ext_cols,
            "materialized_columns": mat_cols,
        }

    @staticmethod
    def _get_columns(schema, table):
        return db_manager.fetch_all(
            """
            SELECT ordinal_position, column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = :schema
              AND table_name = :table
            ORDER BY ordinal_position
            """,
            {"schema": schema, "table": table},
        )
