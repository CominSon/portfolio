"""Разрешение пути проекта отчёта."""

import json
from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report.naming import object_slug_from_table, report_folder_name
from report_mcp_agent.src.utils.safe_path import safe_absolute


def resolve_new_project_path(arguments, cwd=None):
    """
    Корень MCP-проекта = …/<Название отчёта>/<object_slug>/

    Пример: parent/УКП Недельный/ukp_weeks/

    Если передан явный project_path — используем его как object-root
    (должен содержать docs/sql/agent_registry).
    """
    cwd = Path(cwd or Path.cwd())
    project_path = (arguments.get("project_path") or arguments.get("project_root") or "").strip()
    if project_path:
        return safe_absolute(project_path)

    title = (arguments.get("report_title") or "report").strip()
    table = (arguments.get("final_table") or "").strip()
    if "." in table:
        table = table.split(".", 1)[-1]

    report_dir = report_folder_name(title, arguments.get("folder_name"))
    obj_slug = object_slug_from_table(table, arguments.get("object_folder"))

    parent = (arguments.get("parent_path") or "").strip()
    if parent:
        return safe_absolute(Path(parent) / report_dir / obj_slug)

    return safe_absolute(
        cwd / settings.REPORTS_SUBDIR / report_dir / obj_slug
    )


def project_root_from_manifest_file(manifest_file):
    """agent_registry/REPORT_MANIFEST.json → корень проекта; legacy: файл в корне."""
    path = Path(manifest_file)
    if path.parent.name == settings.AGENT_REGISTRY_DIR:
        return path.parent.parent
    return path.parent


def find_projects(search_root, query=None, limit=20):
    root = safe_absolute(search_root)
    query_l = (query or "").strip().lower()
    found = []
    seen = set()
    if not root.is_dir():
        return found
    for path in sorted(root.rglob(settings.MANIFEST_FILENAME)):
        project = project_root_from_manifest_file(path)
        key = str(project)
        if key in seen:
            continue
        seen.add(key)
        title = ""
        try:
            title = (json.loads(path.read_text(encoding="utf-8")).get("report_title") or "")
        except (ValueError, OSError):
            pass
        blob = "{0} {1} {2}".format(project.name, project.parent.name, title).lower()
        if query_l and query_l not in blob:
            continue
        found.append({
            "project_root": str(project),
            "report_title": title,
            "report_folder": project.parent.name,
            "object_folder": project.name,
        })
        if len(found) >= limit:
            break
    return found
