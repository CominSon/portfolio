from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.csv_export import write_sql_to_csv
from gp_mcp_agent.src.utils.identifier_validator import validate_identifier


class CompareFieldValuesTool(BaseTool):
    name = "compare_field_values"
    description = (
        "Сравнить значения колонки в левой таблице с колонкой в правой (anti-join). "
        "В чат — preview до {0} значений; полная выгрузка всех missing_value — "
        "export_csv=true (CSV в gp_mcp_exports проекта) или export_query_csv с тем же SQL."
    ).format(settings.GP_FIELD_COMPARE_PREVIEW_LIMIT)

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "left_schema": {"type": "string"},
                "left_table": {"type": "string"},
                "left_column": {"type": "string"},
                "right_schema": {"type": "string"},
                "right_table": {"type": "string"},
                "right_column": {"type": "string"},
                "left_filter": {"type": "string"},
                "join_extra": {"type": "string"},
                "export_csv": {
                    "type": "boolean",
                    "description": (
                        "true: выгрузить ВСЕ missing_value в CSV (без лимита строк)"
                    ),
                },
                "export_txt": {
                    "type": "boolean",
                    "description": "Устарело: то же, что export_csv",
                },
            },
            "required": [
                "left_schema", "left_table", "left_column",
                "right_schema", "right_table", "right_column",
            ],
        }

    def execute(self, arguments):
        ls = validate_identifier(arguments.get("left_schema", "").strip(), "left_schema")
        lt = validate_identifier(arguments.get("left_table", "").strip(), "left_table")
        lc = validate_identifier(arguments.get("left_column", "").strip(), "left_column")
        rs = validate_identifier(arguments.get("right_schema", "").strip(), "right_schema")
        rt = validate_identifier(arguments.get("right_table", "").strip(), "right_table")
        rc = validate_identifier(arguments.get("right_column", "").strip(), "right_column")

        for s in (ls, rs):
            db_manager.validate_schema(s)

        left_filter = (arguments.get("left_filter") or "").strip()
        join_extra = (arguments.get("join_extra") or "").strip()
        export_csv = bool(arguments.get("export_csv") or arguments.get("export_txt"))

        if left_filter and not _safe_fragment(left_filter):
            raise ValueError("left_filter содержит недопустимые конструкции")
        if join_extra and not _safe_fragment(join_extra):
            raise ValueError("join_extra содержит недопустимые конструкции")

        left_where = ""
        if left_filter:
            left_where = " AND ({0})".format(left_filter)

        join_on = "l.{lc} = r.{rc}".format(lc=lc, rc=rc)
        if join_extra:
            join_on = join_on + " AND (" + join_extra + ")"

        base_sql = """
            SELECT DISTINCT l.{lc} AS missing_value
            FROM {ls}.{lt} l
            LEFT JOIN {rs}.{rt} r
              ON {join_on}
            WHERE l.{lc} IS NOT NULL
              AND r.{rc} IS NULL
              {left_where}
        """.format(
            lc=lc, rc=rc, ls=ls, lt=lt, rs=rs, rt=rt,
            join_on=join_on, left_where=left_where,
        )

        total = int(db_manager.fetch_scalar(
            "SELECT COUNT(*) AS cnt FROM ({0}) sub".format(base_sql)
        ) or 0)

        preview_limit = settings.GP_FIELD_COMPARE_PREVIEW_LIMIT
        row_limit = settings.GP_FIELD_COMPARE_ROW_LIMIT

        sample_rows = db_manager.fetch_all(
            base_sql + " ORDER BY missing_value LIMIT {0}".format(row_limit)
        )
        preview_values = [r.get("missing_value") for r in sample_rows[:preview_limit]]
        truncated = total > row_limit

        export_info = None
        if export_csv:
            export_sql = base_sql + " ORDER BY missing_value"
            prefix = "compare_{0}_{1}_{2}_vs_{3}_{4}_{5}".format(
                ls, lt, lc, rs, rt, rc
            )
            export_info = write_sql_to_csv(
                export_sql,
                prefix,
                column_order=["missing_value"],
            )

        note = (
            "missing_count={0}; в чате preview до {1}. "
            "Полная выгрузка: export_csv=true."
        ).format(total, preview_limit)
        if export_info:
            note = export_info.get("note", note)

        result = {
            "comparison": "values_in_left_not_in_right",
            "left": "{0}.{1}.{2}".format(ls, lt, lc),
            "right": "{0}.{1}.{2}".format(rs, rt, rc),
            "left_filter": left_filter or None,
            "join_extra": join_extra or None,
            "missing_count": total,
            "preview_limit": preview_limit,
            "row_limit": row_limit,
            "preview_values": preview_values,
            "truncated": truncated,
            "note": note,
        }

        if export_info:
            result.update(export_info)
            result["sample_rows"] = sample_rows[:preview_limit]
        else:
            result["sample_rows"] = sample_rows

        return result


def _safe_fragment(fragment):
    lowered = fragment.lower()
    forbidden = [
        ";", "--", "/*", "*/", "insert", "update", "delete",
        "drop", "truncate", "alter", "create", "grant", "execute",
    ]
    for word in forbidden:
        if word in lowered:
            return False
    return True
