"""Ограничение размера ответов MCP для чата GigaCode (лимит контекста LLM)."""

import json

# Лимиты для чата (~128k контекст). 4k символов ≈ 1k токенов на один tool result.
DEFAULT_MAX_CHARS = 6000
REPORT_MAX_CHARS = 4000
GP_MAX_CHARS = 5000
DDL_PREVIEW_CHARS = 800
ARCHITECTURE_TEXT_MAX = 4000


def _json_size(obj):
    return len(json.dumps(obj, ensure_ascii=False, default=str))


def _truncate_text(text, limit, suffix="\n\n...[обрезано для чата, полные данные — в файлах проекта]"):
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit] + suffix


def compact_tool_result(tool_name, result, max_chars=None, server=None):
    if not isinstance(result, dict):
        return result
    if max_chars is None:
        if server == "report":
            max_chars = REPORT_MAX_CHARS
        elif server == "gp":
            max_chars = GP_MAX_CHARS
        else:
            max_chars = DEFAULT_MAX_CHARS

    if tool_name == "get_lineage_diagnostic" and result.get("compact_mode"):
        return result
    if tool_name == "continue_report_build":
        max_chars = 8000
    if tool_name == "resume_report_session":
        max_chars = 8000

    if tool_name == "build_full_lineage":
        result = _compact_lineage(result)
    elif tool_name == "get_function":
        result = _compact_function(result)
    elif tool_name == "get_view_ddl":
        result = _compact_view_ddl(result)
    elif tool_name == "get_table_ddl":
        result = _compact_table_ddl(result)
    elif tool_name == "get_doc_templates":
        result = _compact_doc_templates(result)
    elif tool_name == "get_report_build_spec":
        result = _compact_build_spec(result)
    elif tool_name == "get_report_lineage":
        result = _compact_report_lineage(result)
    elif tool_name == "get_lineage_diagnostic":
        result = _compact_lineage_diagnostic(result)
    if _json_size(result) > max_chars:
        if tool_name == "get_function" and result.get("mode") == "lineage":
            result = _preserve_lineage_fields(result)
        else:
            result = {
                "ok": result.get("ok", True),
                "compact": True,
                "tool": tool_name,
                "summary": _extract_summary(result),
                "truncated": True,
                "hint": (
                    "Ответ обрезан (лимит контекста чата). "
                    "Сохраняйте большие данные через export_query_csv / export_function_ddl, "
                    "не держите в истории чата."
                ),
            }
    return result


def _compact_lineage(result):
    graph = result.get("graph") or {}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    slim_nodes = []
    for node in nodes[:120]:
        slim_nodes.append({
            "id": node.get("id"),
            "node_type": node.get("node_type"),
            "schema": node.get("schema"),
            "name": node.get("name"),
            "role": node.get("role"),
            "candidate_kind": node.get("candidate_kind"),
        })
    slim_edges = []
    for edge in edges[:200]:
        slim_edges.append({
            "from": edge.get("from"),
            "to": edge.get("to"),
            "relation": edge.get("relation"),
        })
    result = dict(result)
    result["graph"] = {
        "nodes": slim_nodes,
        "edges": slim_edges,
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "truncated": len(nodes) > len(slim_nodes) or len(edges) > len(slim_edges),
    }
    if isinstance(result.get("architecture_text"), list):
        text = "\n".join(result["architecture_text"])
    else:
        text = result.get("architecture_text") or ""
    result["architecture_text"] = _truncate_text(text, ARCHITECTURE_TEXT_MAX)
    result["response_mode"] = result.get("response_mode", "summary")
    result["hint"] = (
        "Полный lineage не нужен в чате. DDL — export_function_ddl; в проект отчёта — write_report_file."
    )
    return result


def _compact_function(result):
    result = dict(result)
    if result.get("mode") == "lineage":
        # Для чата ужимаем превью; ключевые поля lineage НЕ трогаем.
        for heavy in ("dml_block_previews", "cte_chain", "union_branches"):
            if heavy in result and result[heavy]:
                result[heavy] = result[heavy][:2] if isinstance(result[heavy], list) else result[heavy]
        previews = result.get("dml_block_previews") or []
        result["dml_block_previews"] = [
            _truncate_text(p, DDL_PREVIEW_CHARS, "\n-- ...") if isinstance(p, str) else p
            for p in previews[:1]
        ]
        result.pop("full_ddl", None)
        result["hint"] = (
            "reads_from_for_lineage / data_reads_from — источники шага. "
            "DDL — export_function_ddl; в проект — report write_report_file."
        )
        return result
    ddl = result.get("full_ddl") or ""
    if ddl:
        result["full_ddl_preview"] = _truncate_text(ddl, DDL_PREVIEW_CHARS, "\n-- ...")
        result.pop("full_ddl", None)
    result["hint"] = "Полный DDL — export_function_ddl (агент пишет sql/ddl через write_report_file)."
    return result


_LINEAGE_KEEP = (
    "mode",
    "procedure",
    "writes_to",
    "write_role",
    "write_roles",
    "branch_role",
    "data_reads_from",
    "reads_from_for_lineage",
    "suggested_reads_from",
    "immediate_reads_from",
    "reference_reads_from",
    "join_reads_in_query",
    "temp_table_lineage",
    "heuristic_limitations",
    "warning",
    "next_step_hint",
    "lineage_probe",
)


def _preserve_lineage_fields(result):
    """Если ответ всё ещё больше лимита — оставить только поля lineage, не summary-заглушку."""
    keep = {k: result[k] for k in _LINEAGE_KEEP if k in result}
    keep["compact"] = True
    keep["truncated_detail"] = True
    return keep


def _compact_table_ddl(result):
    result = dict(result)
    ddl = result.get("ddl") or result.get("full_ddl") or ""
    if ddl:
        result["ddl_preview"] = _truncate_text(ddl, DDL_PREVIEW_CHARS, "\n-- ...")
        result.pop("ddl", None)
        result.pop("full_ddl", None)
    result["hint"] = "Полный DDL — export / write_report_file в sql/ddl/objects/."
    return result


def _compact_doc_templates(result):
    result = dict(result)
    templates = result.get("templates") or {}
    result.pop("templates", None)
    result["doc_files"] = sorted(templates.keys())
    result["hint"] = (
        "Шаблоны уже в проекте после scaffold (docs/*.md). "
        "Документацию пишет агент: render_report_docs + write_report_file."
    )
    return result


def _compact_view_ddl(result):
    result = dict(result)
    ddl = result.get("full_ddl") or result.get("definition") or ""
    if ddl:
        result["full_ddl_preview"] = _truncate_text(ddl, DDL_PREVIEW_CHARS, "\n-- ...")
        result.pop("full_ddl", None)
        result.pop("definition", None)
    refs = result.get("tables_referenced") or []
    if refs:
        result["tables_referenced"] = refs[:8]
        if len(refs) > 8:
            result["tables_referenced_truncated"] = True
    result["upstream_sources"] = result.get("upstream_sources") or [
        r.get("qualified") for r in refs if isinstance(r, dict)
    ]
    result["hint"] = (
        "upstream_sources — источники view. "
        "DDL: export_view_ddl."
    )
    return result


def _compact_report_lineage(result):
    result = dict(result)
    steps = result.get("lineage_steps") or []
    result["lineage_step_count"] = len(steps)
    result["lineage_steps"] = [
        {
            "order": s.get("order"),
            "procedure": s.get("procedure"),
            "writes_to": s.get("writes_to"),
            "reads_from": s.get("reads_from"),
        }
        for s in steps[-6:]
    ]
    if len(steps) > 6:
        result["lineage_steps_truncated"] = True
    for key in ("lineage_steps_by_schedule", "primary_branches", "supplement_branches"):
        if key in result:
            result.pop(key, None)
    result["hint"] = "Полная цепочка в REPORT_MANIFEST.json и checkpoint на диске."
    return result


def _compact_lineage_diagnostic(result):
    if not result.get("compact_mode"):
        return result
    return {
        "ok": result.get("ok"),
        "compact_mode": True,
        "final_object": result.get("final_object"),
        "lineage_step_count": result.get("lineage_step_count"),
        "error_count": result.get("error_count"),
        "warning_count": result.get("warning_count"),
        "frontier": result.get("frontier"),
        "top_gaps": (result.get("gaps") or [])[:5],
        "next_recommended_actions": result.get("next_recommended_actions"),
        "diagnostic_markdown": result.get("diagnostic_markdown"),
        "hint": result.get("hint"),
    }



def _compact_build_spec(result):
    workflow = result.get("workflow") or []
    result["workflow_compact"] = [
        "{0}. {1} ({2})".format(s.get("step"), s.get("tool"), s.get("id"))
        for s in workflow
    ]
    result.pop("workflow", None)
    return result


def _extract_summary(result):
    keys = (
        "ok", "target", "final_object", "project_root", "summary",
        "function_count", "view_count", "message", "hint", "workflow_compact",
        "steps_completed", "issues", "warnings",
    )
    return {k: result[k] for k in keys if k in result}


def dumps_compact(obj):
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))
