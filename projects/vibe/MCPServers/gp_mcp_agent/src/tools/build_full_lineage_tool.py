import re

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.db import db_manager
from gp_mcp_agent.src.tools.base import BaseTool
from gp_mcp_agent.src.utils.gp_function_search import (
    build_search_patterns,
    search_functions_by_pattern,
    search_views_for_table,
)


_TABLE_REF_RE = re.compile(
    r"([a-zA-Z_][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)",
    re.IGNORECASE,
)


class BuildFullLineageTool(BaseTool):
    name = "build_full_lineage"
    description = (
        "Зависимости от витрины до spod_*. "
        "response_mode=summary (по умолчанию) — для чата; full — только если нужен полный graph."
    )

    def input_schema(self):
        return {
            "type": "object",
            "properties": {
                "qualified": {
                    "type": "string",
                    "description": "schema.table",
                },
                "schema": {"type": "string"},
                "table": {"type": "string"},
                "max_depth": {
                    "type": "integer",
                    "description": "Максимальная глубина обхода (1..8), по умолчанию 5",
                },
                "include_columns": {
                    "type": "boolean",
                    "description": "Добавить колонки целевой витрины (по умолчанию false)",
                },
                "response_mode": {
                    "type": "string",
                    "enum": ["summary", "full"],
                    "description": "summary (по умолчанию) — компактно для чата; full — полный graph",
                },
            },
            "required": ["schema", "table"],
        }

    def execute(self, arguments):
        from gp_mcp_agent.src.utils.qualified_name import resolve_schema_name

        schema, table = resolve_schema_name(arguments, name_key="table")
        db_manager.validate_schema(schema)

        max_depth = int(arguments.get("max_depth") or 5)
        max_depth = max(1, min(max_depth, 8))
        include_columns = bool(arguments.get("include_columns"))
        response_mode = (arguments.get("response_mode") or "summary").strip().lower()

        builder = _LineageBuilder(schema, table, max_depth)
        graph = builder.build()
        arch_text = builder.architecture_text(graph)

        result = {
            "target": "{0}.{1}".format(schema, table),
            "max_depth": max_depth,
            "response_mode": response_mode,
            "summary": builder.summary(graph),
            "assumptions": [
                "Все кандидаты наполнения сохраняются, даже при неоднозначности.",
                "Первичные источники определяются как spod_* в схеме *_in.",
                "Рекурсия останавливается на первичном источнике, цикле или max_depth.",
            ],
            "hint": (
                "response_mode=summary для чата. Полный graph — только при необходимости; "
                "детали сохраняйте в файлы проекта отчёта."
            ),
        }

        if response_mode == "full":
            result["graph"] = graph
            result["architecture_text"] = arch_text
        else:
            nodes = graph.get("nodes") or []
            result["graph_preview"] = {
                "nodes_sample": [
                    {
                        "node_type": n.get("node_type"),
                        "schema": n.get("schema"),
                        "name": n.get("name"),
                        "role": n.get("role"),
                    }
                    for n in nodes[:40]
                ],
                "nodes_total": len(nodes),
                "edges_total": len(graph.get("edges") or []),
            }
            if isinstance(arch_text, list):
                arch_text = "\n".join(arch_text)
            result["architecture_text"] = arch_text[:4000] + (
                "\n..." if len(arch_text) > 4000 else ""
            )

        if include_columns:
            result["target_columns"] = db_manager.fetch_all(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = :schema
                  AND table_name = :table
                ORDER BY ordinal_position
                """,
                {"schema": schema, "table": table},
            )

        return result


class _LineageBuilder(object):
    def __init__(self, root_schema, root_table, max_depth):
        self.root_schema = root_schema
        self.root_table = root_table
        self.max_depth = max_depth
        self.allowed_schemas = settings.GP_ALLOWED_SCHEMAS
        self.allowed_schemas_l = [s.lower() for s in self.allowed_schemas]

        self.nodes = {}
        self.edges = []
        self.visited_tables = set()
        self.function_cache = {}

    def build(self):
        root_id = _table_id(self.root_schema, self.root_table)
        self.nodes[root_id] = {
            "id": root_id,
            "node_type": "table",
            "schema": self.root_schema,
            "name": self.root_table,
            "role": "target_mart",
        }
        self._walk_table(self.root_schema, self.root_table, depth=0)
        return {"nodes": list(self.nodes.values()), "edges": self.edges}

    def _walk_table(self, schema, table, depth):
        table_key = "{0}.{1}".format(schema.lower(), table.lower())
        if table_key in self.visited_tables:
            return
        self.visited_tables.add(table_key)

        if depth >= self.max_depth:
            return

        candidates = self._find_function_candidates(schema, table)
        table_node_id = _table_id(schema, table)

        writer_candidates = [c for c in candidates if c["candidate_kind"] != "reference_only"]
        if writer_candidates:
            selected = writer_candidates
        else:
            selected = candidates

        for fn in selected:
            fn_node_id = _function_id(fn["schema_name"], fn["function_name"], fn["arguments"])
            if fn_node_id not in self.nodes:
                self.nodes[fn_node_id] = {
                    "id": fn_node_id,
                    "node_type": "function",
                    "schema": fn["schema_name"],
                    "name": fn["function_name"],
                    "arguments": fn["arguments"],
                    "owner": fn["owner"],
                    "candidate_kind": fn["candidate_kind"],
                    "match_mode": fn["match_mode"],
                }

            self.edges.append({
                "from": table_node_id,
                "to": fn_node_id,
                "relation": "filled_by_candidate_function",
                "candidate_kind": fn["candidate_kind"],
            })

            src_tables = self._extract_source_tables(fn["definition"])
            for src in src_tables:
                src_schema, src_table = src
                src_id = _table_id(src_schema, src_table)
                if src_id not in self.nodes:
                    self.nodes[src_id] = {
                        "id": src_id,
                        "node_type": "table",
                        "schema": src_schema,
                        "name": src_table,
                        "role": (
                            "primary_source"
                            if _is_primary_source(src_schema, src_table)
                            else "intermediate_source"
                        ),
                    }

                self.edges.append({
                    "from": fn_node_id,
                    "to": src_id,
                    "relation": "reads_from",
                })

                if not _is_primary_source(src_schema, src_table):
                    self._walk_table(src_schema, src_table, depth + 1)

        views = self._find_views_for_table(schema, table)
        for v in views:
            view_id = _view_id(v["schema_name"], v["view_name"])
            if view_id not in self.nodes:
                self.nodes[view_id] = {
                    "id": view_id,
                    "node_type": "view",
                    "schema": v["schema_name"],
                    "name": v["view_name"],
                    "role": "candidate_view_dependency",
                }
            self.edges.append({
                "from": table_node_id,
                "to": view_id,
                "relation": "referenced_in_view",
            })

    def _find_function_candidates(self, schema, table):
        cache_key = "{0}.{1}".format(schema.lower(), table.lower())
        if cache_key in self.function_cache:
            return self.function_cache[cache_key]

        patterns = build_search_patterns(schema, table, "both")

        dedup = {}
        for pat in patterns:
            rows = search_functions_by_pattern(pat)
            for row in rows:
                key = _function_id(row["schema_name"], row["function_name"], row["arguments"])
                kind = _classify_candidate(row["definition"], schema, table, pat)
                row["candidate_kind"] = kind
                row["match_mode"] = "both"
                if key not in dedup:
                    dedup[key] = row
                elif _candidate_rank(kind) > _candidate_rank(dedup[key]["candidate_kind"]):
                    dedup[key]["candidate_kind"] = kind

        out = list(dedup.values())
        self.function_cache[cache_key] = out
        return out

    @staticmethod
    def _query_functions(pattern):
        return search_functions_by_pattern(pattern)

    @staticmethod
    def _find_views_for_table(schema, table):
        return search_views_for_table(schema, table)

    def _extract_source_tables(self, ddl_text):
        if not ddl_text:
            return []
        out = {}
        for sch, tbl in _TABLE_REF_RE.findall(ddl_text):
            sch_l = sch.lower()
            if sch_l in self.allowed_schemas_l:
                sch_norm = self.allowed_schemas[self.allowed_schemas_l.index(sch_l)]
                key = "{0}.{1}".format(sch_norm.lower(), tbl.lower())
                out[key] = (sch_norm, tbl)
        return list(out.values())[: settings.GP_LINEAGE_FUNCTION_SEARCH_LIMIT]

    def architecture_text(self, graph):
        root = _table_id(self.root_schema, self.root_table)
        adjacency = {}
        for e in graph["edges"]:
            adjacency.setdefault(e["from"], []).append(e)

        node_map = dict((n["id"], n) for n in graph["nodes"])
        lines = []
        visited_path = set()

        def _dfs(node_id, level):
            node = node_map.get(node_id, {"id": node_id, "node_type": "unknown"})
            prefix = "  " * level + "- "
            lines.append(prefix + _node_label(node))

            if node_id in visited_path:
                lines.append("  " * (level + 1) + "* cycle detected")
                return

            visited_path.add(node_id)
            for edge in adjacency.get(node_id, []):
                relation = edge.get("relation")
                rel_line = "  " * (level + 1) + "> " + relation
                if edge.get("candidate_kind"):
                    rel_line += " ({0})".format(edge.get("candidate_kind"))
                lines.append(rel_line)
                _dfs(edge["to"], level + 2)
            visited_path.remove(node_id)

        _dfs(root, 0)
        return lines

    @staticmethod
    def summary(graph):
        nodes = graph["nodes"]
        edges = graph["edges"]
        table_nodes = [n for n in nodes if n.get("node_type") == "table"]
        fn_nodes = [n for n in nodes if n.get("node_type") == "function"]
        primary_sources = [
            n for n in table_nodes if n.get("role") == "primary_source"
        ]
        candidate_kinds = {}
        for f in fn_nodes:
            k = f.get("candidate_kind") or "unknown"
            candidate_kinds[k] = candidate_kinds.get(k, 0) + 1
        return {
            "nodes_total": len(nodes),
            "edges_total": len(edges),
            "tables_total": len(table_nodes),
            "functions_total": len(fn_nodes),
            "primary_sources_total": len(primary_sources),
            "candidate_kind_stats": candidate_kinds,
        }


def _table_id(schema, table):
    return "table:{0}.{1}".format(schema, table)


def _function_id(schema, name, args):
    return "function:{0}.{1}({2})".format(schema, name, args or "")


def _view_id(schema, name):
    return "view:{0}.{1}".format(schema, name)


def _is_primary_source(schema, table):
    return schema.lower().endswith("_in") and table.lower().startswith("spod_")


def _candidate_rank(kind):
    rank = {
        "candidate_insert": 5,
        "candidate_update": 4,
        "candidate_merge_like": 3,
        "candidate_delete_or_truncate": 2,
        "reference_only": 1,
    }
    return rank.get(kind, 0)


def _classify_candidate(ddl, schema, table, pattern):
    text = (ddl or "").lower()
    qualified = "{0}.{1}".format(schema.lower(), table.lower())
    bare = table.lower()
    pat = (pattern or "").strip("%").lower()

    has_qualified = qualified in text or pat in text
    has_bare = bare in text or pat.endswith(bare)
    if not has_qualified and not has_bare:
        return "reference_only"

    patterns = [
        (r"\binsert\s+into\s+{0}\b".format(re.escape(qualified)), "candidate_insert"),
        (r"\bupdate\s+{0}\b".format(re.escape(qualified)), "candidate_update"),
        (r"\bmerge\s+into\s+{0}\b".format(re.escape(qualified)), "candidate_merge_like"),
        (
            r"\b(delete\s+from|truncate\s+table)\s+{0}\b".format(re.escape(qualified)),
            "candidate_delete_or_truncate",
        ),
        (r"\binsert\s+into\s+{0}\b".format(re.escape(bare)), "candidate_insert"),
        (r"\bupdate\s+{0}\b".format(re.escape(bare)), "candidate_update"),
        (r"\bmerge\s+into\s+{0}\b".format(re.escape(bare)), "candidate_merge_like"),
    ]
    for pattern, kind in patterns:
        if re.search(pattern, text):
            return kind
    return "reference_only"


def _node_label(node):
    t = node.get("node_type")
    if t == "table":
        role = node.get("role")
        base = "{0}.{1}".format(node.get("schema"), node.get("name"))
        if role:
            return "TABLE {0} [{1}]".format(base, role)
        return "TABLE {0}".format(base)
    if t == "function":
        return "FUNCTION {0}.{1}({2}) [{3}]".format(
            node.get("schema"),
            node.get("name"),
            node.get("arguments") or "",
            node.get("candidate_kind"),
        )
    if t == "view":
        return "VIEW {0}.{1}".format(node.get("schema"), node.get("name"))
    return str(node.get("id"))
