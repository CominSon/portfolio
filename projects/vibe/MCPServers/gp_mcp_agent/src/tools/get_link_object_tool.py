"""Tool: тонкая обёртка над f_get_link_object — без классификации writers."""

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.link_object_search import call_link_object_raw
from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name


class GetLinkObjectTool(BaseTool):
    name = "get_link_object"
    description = (
        "Тонкая обёртка work.f_get_link_object: вернуть ВСЕ найденные "
        "schemaname/proname без фильтров и без классификации DML. "
        "Дальше агент сам смотрит каждую функцию через get_function и решает, "
        "есть ли связь (INSERT/UPDATE/чтение)."
    )

    def input_schema(self):
        return {
            "type": "object",
            "additionalProperties": True,
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": (
                        "Паттерн для f_get_link_object — обычно имя таблицы "
                        "(как при ручном SELECT FROM f_get_link_object(...))"
                    ),
                },
                "qualified": {
                    "type": "string",
                    "description": "schema.table — в функцию уйдёт имя таблицы (без схемы)",
                },
                "schema": {"type": "string"},
                "table": {"type": "string"},
                "filter_schema": {
                    "type": "string",
                    "description": "2-й аргумент f_get_link_object (по умолчанию '')",
                },
                "filter_proname": {
                    "type": "string",
                    "description": "3-й аргумент f_get_link_object (по умолчанию '')",
                },
            },
        }

    def execute(self, arguments):
        obj = (arguments.get("object_name") or "").strip()
        table = (arguments.get("table") or "").strip()

        if not obj:
            target = (arguments.get("qualified") or "").strip()
            if target and "." in target:
                _, table = target.split(".", 1)
                obj = table.strip()
            else:
                try:
                    _, table = resolve_schema_name(arguments, name_key="table")
                    obj = table
                except ValueError:
                    obj = table

        if not obj:
            raise ValueError(
                "Укажите object_name (как в ручном f_get_link_object) "
                "или qualified / schema+table"
            )

        fs = arguments.get("filter_schema") or ""
        fp = arguments.get("filter_proname") or ""
        fn_schema = settings.GP_DEFAULT_PROCEDURE_SCHEMA
        fn_name = getattr(settings, "GP_LINK_OBJECT_FUNCTION", "f_get_link_object")

        rows, source_tag = call_link_object_raw(obj, fs, fp)
        source = (
            "{0}.{1}".format(fn_schema, fn_name)
            if source_tag == "f_get_link_object"
            else source_tag
        )

        results = []
        seen = set()
        for row in rows:
            sch = row.get("schemaname")
            name = row.get("proname")
            key = (sch, name)
            if not sch or not name or key in seen:
                continue
            seen.add(key)
            item = {"schemaname": sch, "proname": name}
            if row.get("kind"):
                item["kind"] = row.get("kind")
            results.append(item)

        names = ["{0}.{1}".format(r["schemaname"], r["proname"]) for r in results]

        return {
            "object_name": obj,
            "filter_schema": fs or "",
            "filter_proname": fp or "",
            "source": source,
            "row_count": len(results),
            "rows": results,
            "names": names,
            "hint": (
                "Сырой список как у f_get_link_object — без отбора writers. "
                "Дальше: для каждого имени get_function → агент сам решает, "
                "есть ли нужная связь, и регистрирует lineage."
            ),
        }
