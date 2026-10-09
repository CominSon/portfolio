"""Чтение/запись файлов внутри проекта отчёта."""

from pathlib import Path

from report_mcp_agent.src.report import layout, manifest
from report_mcp_agent.src.utils.safe_path import safe_absolute, write_text_safe


def write_project_file(project_root, relative_path, content, register_ddl=False):
    data = manifest.require_manifest(project_root)
    rel = (relative_path or "").replace("\\", "/").lstrip("/")
    if not layout.relative_allowed(rel):
        raise ValueError("Путь не разрешён: {0}".format(rel))

    root = safe_absolute(project_root)
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    body = content if content is not None else ""
    try:
        from mcp_workspace_config.text_normalize import normalize_file_content
        body = normalize_file_content(body, rel)
    except Exception:
        body = str(body).replace("\r\n", "\n").replace("\r", "\n")
    write_text_safe(target, body)

    if rel.startswith("sql/ddl/objects/") and register_ddl:
        entry = rel.replace("\\", "/")
        lst = data.setdefault("ddl_objects", [])
        if entry not in lst:
            lst.append(entry)
    if rel.startswith("sql/ddl/functions/") and register_ddl:
        entry = rel
        lst = data.setdefault("ddl_functions", [])
        if entry not in lst:
            lst.append(entry)
    if rel.startswith("docs/"):
        lst = data.setdefault("doc_files", [])
        if rel not in lst:
            lst.append(rel)
    if rel.startswith("sql/dml/"):
        lst = data.setdefault("dml_files", [])
        if rel not in lst:
            lst.append(rel)

    manifest.save_manifest(project_root, data)
    return {"ok": True, "path": str(target), "relative_path": rel, "bytes": len(body or "")}


def read_project_file(project_root, relative_path, max_chars=200000):
    manifest.require_manifest(project_root)
    rel = (relative_path or "").replace("\\", "/").lstrip("/")
    if not layout.relative_allowed(rel):
        raise ValueError("Путь не разрешён: {0}".format(rel))
    path = safe_absolute(project_root) / rel
    if not path.is_file():
        raise ValueError("Файл не найден: {0}".format(rel))
    text = path.read_text(encoding="utf-8")
    truncated = False
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
        truncated = True
    return {
        "ok": True,
        "relative_path": rel,
        "content": text,
        "truncated": truncated,
        "size": path.stat().st_size,
    }


def list_project_files(project_root, prefix=None):
    manifest.require_manifest(project_root)
    root = safe_absolute(project_root)
    prefix = (prefix or "").replace("\\", "/").lstrip("/")
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(p in path.parts for p in (".git", "__pycache__", "logs", "agent_registry")):
            continue
        rel = path.relative_to(root).as_posix()
        if prefix and not rel.startswith(prefix):
            continue
        files.append({"relative_path": rel, "size": path.stat().st_size})
    return {"ok": True, "files": files, "count": len(files)}
