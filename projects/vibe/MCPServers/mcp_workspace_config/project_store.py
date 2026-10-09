"""Общий путь проекта IDEA для всех MCP-серверов (GP, Bitbucket)."""

import json
import os
from pathlib import Path

from mcp_workspace_config.safe_path import safe_absolute, safe_module_dir

_FILENAME = "project_path.json"
_ROOT = safe_module_dir(__file__)


def _config_path():
    return _ROOT / _FILENAME


def load_shared_project():
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return {}


def save_shared_project(project_path, source="manual", note=None):
    path = _config_path()
    data = {
        "project_path": project_path,
        "source": source,
        "note": note,
    }
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return {"shared_config_path": str(path), **data}


def get_shared_project_path():
    return (load_shared_project().get("project_path") or "").strip()


def _normalize_env_path(value):
    value = (value or "").strip().strip('"').strip("'")
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    return str(safe_absolute(path))


def path_from_ide_env():
    for key in (
        "MCP_PROJECT_PATH",
        "GP_PROJECT_PATH",
        "BB_PROJECT_PATH",
        "IDEA_INITIAL_DIRECTORY",
        "PROJECT_DIR",
        "WORKSPACE_FOLDER",
    ):
        value = os.environ.get(key, "").strip()
        if value:
            normalized = _normalize_env_path(value)
            if normalized and Path(normalized).is_dir():
                return normalized, "env:{0}".format(key)
    return None, None
