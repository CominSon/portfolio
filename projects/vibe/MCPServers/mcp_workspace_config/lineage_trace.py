"""JSONL-трассировка анализа lineage (общий модуль для MCP)."""

import json
from datetime import datetime
from pathlib import Path

from mcp_workspace_config.safe_path import safe_absolute, write_text_safe

TRACE_DIR = "logs"
TRACE_JSONL = "logs/lineage_trace.jsonl"


def trace_path(project_root):
    return safe_absolute(project_root) / TRACE_JSONL


def ensure_trace_dir(project_root):
    path = safe_absolute(project_root) / TRACE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def next_seq(manifest):
    seq = int((manifest or {}).get("lineage_trace_seq") or 0) + 1
    if manifest is not None:
        manifest["lineage_trace_seq"] = seq
    return seq


def append_event(project_root, event_type, payload, manifest=None, seq=None):
    """Добавить событие в lineage_trace.jsonl. Возвращает seq."""
    ensure_trace_dir(project_root)
    if seq is None:
        seq = next_seq(manifest) if manifest is not None else _peek_seq(project_root) + 1
    event = {
        "seq": seq,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "type": event_type,
        "payload": payload or {},
    }
    path = trace_path(project_root)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return seq


def _peek_seq(project_root):
    events = read_events(project_root, limit=1)
    if not events:
        return 0
    return int(events[-1].get("seq") or 0)


def read_events(project_root, limit=None):
    path = trace_path(project_root)
    if not path.is_file():
        return []
    events = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit is not None and limit > 0:
        return events[-limit:]
    return events


def summarize_tool_result(tool_name, result):
    """Короткое резюме ответа tool для лога (без DDL)."""
    if not isinstance(result, dict):
        return {"raw_type": type(result).__name__}

    skip_keys = {"full_ddl", "definition", "content", "dml_block_previews"}
    out = {}
    for key, value in result.items():
        if key in skip_keys:
            if key == "full_ddl":
                out[key] = "<omitted>"
            elif key == "dml_block_previews" and isinstance(value, list):
                out[key] = ["<{0} chars>".format(len(str(v))) for v in value[:3]]
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            if isinstance(value, str) and len(value) > 500:
                out[key] = value[:500] + "…"
            else:
                out[key] = value
        elif isinstance(value, list):
            out[key] = value[:20] if len(value) <= 20 else value[:20] + ["…+{0}".format(len(value) - 20)]
        elif isinstance(value, dict):
            out[key] = summarize_tool_result(tool_name, value)
    out["_tool"] = tool_name
    return out
