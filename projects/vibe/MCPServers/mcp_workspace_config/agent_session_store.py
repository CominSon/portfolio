"""Реестр вызовов tools в папке проекта отчёта (до удаления проекта).

agent_registry/ — единое хранилище report-project-mcp + gp-greenplum-mcp.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from mcp_workspace_config.safe_path import safe_absolute, write_text_safe

REGISTRY_DIRNAME = "agent_registry"
CHECKPOINT_FILE = "checkpoint.json"
META_FILE = "meta.json"
ARTIFACTS_DIR = "artifacts"
TOOL_CALLS_JSONL = "tool_calls.jsonl"
RESUME_MD = "RESUME.md"

SPILL_KEYS = frozenset({
    "full_ddl",
    "ddl",
    "definition",
    "dml_block_previews",
    "lineage_steps",
    "lineage_steps_by_schedule",
    "timeline",
    "graph",
    "templates",
    "architecture_text",
    "primary_branches",
    "supplement_branches",
    "inventory",
    "gaps",
    "lineage_validation",
})

_GP_SPILL_TOOLS = frozenset({
    "get_function",
    "export_function_ddl",
    "export_view_ddl",
    "get_table_ddl",
    "get_view_ddl",
    "find_functions_for_table",
    "verify_object_terminal",
    "get_object_info",
    "get_procedure_schedule",
    "search_tables",
    "get_columns",
    "explain",
    "run_select",
})


def registry_dir(project_root):
    d = safe_absolute(project_root) / REGISTRY_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    (d / ARTIFACTS_DIR).mkdir(exist_ok=True)
    return d


def _meta_path(project_root):
    return registry_dir(project_root) / META_FILE


def _append_tool_call(project_root, entry):
    path = registry_dir(project_root) / TOOL_CALLS_JSONL
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _next_artifact_seq(project_root):
    path = _meta_path(project_root)
    meta = {}
    if path.is_file():
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            meta = {}
    seq = int(meta.get("artifact_seq") or 0) + 1
    meta["artifact_seq"] = seq
    meta["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_text_safe(path, json.dumps(meta, ensure_ascii=False, indent=2))
    return seq


def _server_slug(mcp_server):
    s = (mcp_server or "mcp").lower()
    if "gp" in s or "greenplum" in s:
        return "gp"
    if "report" in s:
        return "report"
    return re.sub(r"[^\w]+", "_", s)[:12]


def spill_tool_result(project_root, tool_name, arguments, result, mcp_server="report-project"):
    if not project_root or not isinstance(result, dict):
        return result

    seq = _next_artifact_seq(project_root)
    srv = _server_slug(mcp_server)
    safe_tool = re.sub(r"[^\w.-]+", "_", tool_name or "tool")[:36]
    artifact_name = "{0:04d}_{1}_{2}.json".format(seq, srv, safe_tool)
    artifact_path = registry_dir(project_root) / ARTIFACTS_DIR / artifact_name

    payload = {
        "seq": seq,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "mcp_server": mcp_server,
        "tool": tool_name,
        "arguments": _slim_args(arguments),
        "result": result,
    }
    write_text_safe(
        artifact_path,
        json.dumps(payload, ensure_ascii=False, default=str, indent=2),
    )
    _append_tool_call(
        project_root,
        {
            "seq": seq,
            "ts": payload["ts"],
            "mcp_server": mcp_server,
            "tool": tool_name,
            "artifact": artifact_name,
            "summary": _one_line_summary(tool_name, result),
        },
    )

    slim = _slim_for_chat(result)
    slim["registry_artifact"] = artifact_name
    slim["registry_dir"] = str(registry_dir(project_root))
    slim["_spilled"] = True
    return slim


def _one_line_summary(tool_name, result):
    if not isinstance(result, dict):
        return str(tool_name)
    parts = [tool_name]
    for key in ("procedure", "writes_to", "target", "target_object", "final_object", "ok"):
        if result.get(key) is not None:
            parts.append("{0}={1}".format(key, result.get(key)))
    return " ".join(parts)[:200]


def _slim_args(arguments):
    out = {}
    for k, v in (arguments or {}).items():
        if isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "…"
        else:
            out[k] = v
    return out


def _slim_for_chat(result):
    out = {}
    for key, value in result.items():
        if key in SPILL_KEYS:
            if key == "lineage_steps" and isinstance(value, list):
                out["lineage_step_count"] = len(value)
                out["lineage_steps_summary"] = [
                    {
                        "order": s.get("order"),
                        "procedure": s.get("procedure"),
                        "writes_to": s.get("writes_to"),
                    }
                    for s in value[:8]
                ]
            elif key == "gaps" and isinstance(value, list):
                out["gap_count"] = len(value)
                out["top_gaps"] = value[:5]
            elif key == "dml_block_previews":
                out[key] = ["<в agent_registry/artifacts>"]
            elif key in ("full_ddl", "ddl", "definition"):
                out[key + "_chars"] = len(value or "")
            else:
                out[key] = "<в agent_registry>"
        else:
            out[key] = value
    return out


def load_checkpoint(project_root):
    path = registry_dir(project_root) / CHECKPOINT_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_checkpoint(project_root, data):
    path = registry_dir(project_root) / CHECKPOINT_FILE
    data = dict(data or {})
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    data["project_root"] = str(project_root)
    data["registry_dir"] = str(registry_dir(project_root))
    write_text_safe(
        path,
        json.dumps(data, ensure_ascii=False, indent=2),
    )
    _write_resume_md(project_root, data)
    return str(path)


def update_checkpoint_from_manifest(project_root, manifest, last_tool=None, mcp_server=None, extra=None):
    if not manifest:
        return None
    inv = manifest.get("inventory") or {}
    frontier = manifest.get("lineage_frontier") or {}
    steps = manifest.get("lineage_steps") or []
    phase = "lineage_analysis"
    if manifest.get("analysis_complete"):
        ddl = manifest.get("ddl_inventory") or {}
        phase = "ddl_export" if not ddl.get("objects") else "docs"
    if "technical_generated" in (manifest.get("steps_completed") or []):
        phase = "validate"

    cp = {
        "project_root": str(project_root),
        "report_title": manifest.get("report_title"),
        "final_object": manifest.get("final_object"),
        "lineage_step_count": len(steps),
        "analysis_complete": bool(manifest.get("analysis_complete")),
        "frontier_pending": frontier.get("pending") or [],
        "terminal_sources": inv.get("terminal_sources") or [],
        "last_lineage_step": steps[-1] if steps else None,
        "last_tool": last_tool,
        "last_mcp_server": mcp_server,
        "phase": phase,
        "steps_completed": manifest.get("steps_completed") or [],
    }
    if extra:
        cp.update(extra)
    return save_checkpoint(project_root, cp)


def _write_resume_md(project_root, cp):
    title = cp.get("report_title") or "отчёт"
    lines = [
        "# {0}".format(title),
        "",
        "Проект: `{0}`".format(cp.get("project_root")),
        "Фаза: **{0}** | шагов lineage: {1}".format(
            cp.get("phase"), cp.get("lineage_step_count")
        ),
        "",
        "## Продолжить (человеческим языком)",
        "",
        "Скажите агенту, например:",
        "",
        '> Найди проект «{0}» и продолжи сборку отчёта'.format(title),
        "",
        "Агент вызовет `resume_report_project` → `get_report_context` и доработает через GP + upsert/write.",
        "",
        "## Frontier",
    ]
    pending = cp.get("frontier_pending") or []
    lines.extend(["- `{0}`".format(p) for p in pending] or ["- _пуст_"])
    lines.append("")
    write_text_safe(registry_dir(project_root) / RESUME_MD, "\n".join(lines))


def load_artifact(project_root, artifact_name):
    path = registry_dir(project_root) / ARTIFACTS_DIR / artifact_name
    if not path.is_file():
        raise FileNotFoundError("Артефакт не найден: {0}".format(artifact_name))
    return json.loads(path.read_text(encoding="utf-8"))


def build_resume_packet(project_root, manifest, diagnostic=None):
    if manifest:
        update_checkpoint_from_manifest(project_root, manifest)
    cp = load_checkpoint(project_root) or {}

    steps = (manifest or {}).get("lineage_steps") or []
    diag = diagnostic or {}
    gaps = (diag.get("top_gaps") or diag.get("gaps") or [])[:5]
    next_actions = diag.get("next_recommended_actions") or []
    if not next_actions and cp.get("frontier_pending"):
        next_actions = [
            "get_report_context → GP find_functions_for_table / upsert_lineage_step"
        ]
    title = cp.get("report_title") or (manifest or {}).get("report_title")
    return {
        "ok": True,
        "resume": True,
        "report_title": title,
        "project_root": str(project_root),
        "registry_dir": str(registry_dir(project_root)),
        "checkpoint": cp,
        "lineage_step_count": len(steps),
        "last_steps": [
            {
                "order": s.get("order"),
                "procedure": s.get("procedure"),
                "writes_to": s.get("writes_to"),
                "reads_from": s.get("reads_from"),
            }
            for s in steps[-4:]
        ],
        "frontier_pending": cp.get("frontier_pending") or [],
        "phase": cp.get("phase"),
        "analysis_complete": cp.get("analysis_complete"),
        "top_gaps": gaps,
        "next_actions": next_actions,
        "hint": (
            "Состояние в папке проекта: agent_registry/. "
            "Полные ответы GP и report — в artifacts/. Чат не дублировать."
        ),
    }


def gp_should_spill(tool_name):
    return tool_name in _GP_SPILL_TOOLS
