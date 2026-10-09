"""Каталог выгрузок: <проект>/export или GP_MCP_EXPORT_DIR."""

import os
from datetime import datetime
from pathlib import Path

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.utils import project_store
from gp_mcp_agent.src.utils.safe_path import safe_absolute


def project_exports_dir():
    # type: () -> Path
    custom = os.environ.get("GP_MCP_EXPORT_DIR", "").strip()
    if custom:
        path = Path(custom)
    else:
        project_root, _ = project_store.resolve_effective_project_root(allow_missing=True)
        if project_root:
            path = Path(project_root) / settings.GP_EXPORT_SUBDIR
        else:
            path = Path(os.getcwd()) / settings.GP_EXPORT_SUBDIR

    try:
        path.mkdir(parents=True, exist_ok=True)
        return path
    except OSError:
        fallback = Path(__file__).resolve().parents[2] / settings.GP_EXPORT_SUBDIR
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def display_path(path):
    # type: (Path) -> str
    return str(safe_absolute(path))


def timestamped_filename(prefix, suffix="csv"):
    # type: (str, str) -> str
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in prefix)
    return "{0}_{1}.{2}".format(safe[:120], ts, suffix)


def export_result(path, row_count, columns, extra=None):
    # type: (Path, int, list, dict) -> dict
    exports_dir = display_path(path.parent)
    project_root, project_source = project_store.resolve_effective_project_root(allow_missing=True)
    result = {
        "ok": True,
        "format": "csv",
        "export_path": display_path(path),
        "exports_directory": exports_dir,
        "project_path": project_root,
        "project_source": project_source,
        "working_directory": os.getcwd(),
        "exported_rows": row_count,
        "columns": columns,
        "note": (
            "Полная выгрузка в CSV. Файл: {0}".format(display_path(path))
        ),
    }
    if extra:
        result.update(extra)
    if project_root is None:
        result["hint"] = "Вызовите set_project_path — CSV сохранится в <проект>/export/."
    return result
