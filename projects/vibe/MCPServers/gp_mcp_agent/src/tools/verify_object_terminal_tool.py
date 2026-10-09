from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.gp_function_search import (
    search_functions_for_table,
    search_views_for_table,
)
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name
from gp_mcp_agent.src.utils.write_classifier import (
    classify_write_to_table,
    resolve_exclude_suffixes,
    write_roles_summary,
)


class VerifyObjectTerminalTool(BaseTool):
    name = "verify_object_terminal"
    description = (
        "Проверить, терминальный ли объект (нет процедур наполнения). "
        "Вызывать ПЕРЕД добавлением в terminal_sources. "
        "Если writers не пуст — анализ нужно продолжить (get_function → frontier)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {"type": "string", "description": "schema.table"},
                "schema": {"type": "string"},
                "table": {"type": "string"},
                "exclude_name_suffixes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "exclude_dtl": {"type": "boolean"},
            },
        }

    def execute(self, arguments):
        schema, table = resolve_schema_name(arguments, name_key="table")
        db_manager.validate_schema(schema)

        suffixes = resolve_exclude_suffixes(
            arguments.get("exclude_name_suffixes"),
            bool(arguments.get("exclude_dtl")),
        )

        functions, _ = search_functions_for_table(
            schema, table, mode="both", exclude_name_suffixes=suffixes or None
        )
        views = search_views_for_table(schema, table)

        writers = []
        for row in functions:
            body = row.get("definition") or ""
            roles = classify_write_to_table(body, schema, table)
            if roles:
                writers.append({
                    "qualified": "{0}.{1}".format(
                        row.get("schema_name"), row.get("function_name")
                    ),
                    "write_roles": roles,
                    "write_role": write_roles_summary(roles),
                })

        is_terminal = len(writers) == 0
        qualified = "{0}.{1}".format(schema, table)

        if is_terminal:
            verdict = "terminal"
            hint = (
                "Можно добавить в terminal_sources. "
                "Убедитесь, что в коде builder'ов выше нет скрытых источников (динамический SQL)."
            )
        else:
            verdict = "intermediate"
            hint = (
                "НЕ терминальный источник. writers наполняют объект — "
                "вызовите get_function для builder, извлеките reads_from, "
                "продолжите цикл find_functions_for_table для каждого источника."
            )

        return {
            "qualified": qualified,
            "is_terminal": is_terminal,
            "verdict": verdict,
            "writer_count": len(writers),
            "writers": writers,
            "dependent_views": views,
            "must_continue_analysis": not is_terminal,
            "lineage_probe": {
                "gp_tool": "verify_object_terminal",
                "target_object": qualified,
                "is_terminal": is_terminal,
            },
            "hint": hint,
        }
