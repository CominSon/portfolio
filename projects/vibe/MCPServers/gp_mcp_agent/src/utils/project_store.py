"""Путь открытого проекта IDEA для выгрузок CSV."""

import json
import os
from pathlib import Path

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.utils.safe_path import package_root, safe_absolute

_GP_IDE_ENV_KEYS = (
    "MCP_PROJECT_PATH",
    "GP_PROJECT_PATH",
    "IDEA_INITIAL_DIRECTORY",
    "PROJECT_DIR",
    "WORKSPACE_FOLDER",
)


def _config_dir():
    base = package_root(__file__) / settings.PROFILE_SUBDIR
    base.mkdir(parents=True, exist_ok=True)
    return base


def _profile_path():
    return _config_dir() / settings.PROFILE_FILENAME


def load_profile():
    path = _profile_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (ValueError, OSError):
        return {}


def save_profile(data):
    path = _profile_path()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return {"profile_path": str(path), "saved": True}


def _normalize_path(path_str):
    path_str = (path_str or "").strip().strip('"').strip("'")
    if not path_str:
        raise ValueError("Путь к проекту пустой")
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    resolved = safe_absolute(path)
    if not resolved.is_dir():
        raise ValueError("Папка не существует: {0}".format(resolved))
    return str(resolved)


def get_saved_project_path():
    return (load_profile().get("project_path") or "").strip()


def set_saved_project_path(path, note=None):
    normalized = _normalize_path(path)
    data = load_profile()
    data["project_path"] = normalized
    if note:
        data["note"] = note
    result = save_profile(data)
    result["project_path"] = normalized
    result["config_directory"] = str(_config_dir())
    try:
        from mcp_workspace_config.project_store import save_shared_project
        shared = save_shared_project(normalized, source="gp_mcp", note=note)
        result["shared_config_path"] = shared.get("shared_config_path")
    except Exception:
        pass
    return result


def _path_from_env():
    for key in _GP_IDE_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            try:
                return _normalize_path(value), "env:{0}".format(key)
            except ValueError:
                continue
    return None, None


def _auto_save_if_from_env(path, source):
    """Сохранить путь из env IDEA как default, если ещё не зафиксирован."""
    if not path:
        return False
    if get_saved_project_path():
        return False
    try:
        set_saved_project_path(path, note="auto:{0}".format(source))
        return True
    except ValueError:
        return False


def resolve_effective_project_root(allow_missing=False):
    saved = get_saved_project_path()
    if saved:
        return saved, "saved"
    try:
        from mcp_workspace_config.project_store import get_shared_project_path
        shared = get_shared_project_path()
        if shared:
            return shared, "shared"
    except Exception:
        pass
    env_root, env_src = _path_from_env()
    if env_root:
        auto = _auto_save_if_from_env(env_root, env_src)
        source = "{0}:auto_saved".format(env_src) if auto else env_src
        return env_root, source
    cwd = os.getcwd()
    if cwd and Path(cwd).is_dir():
        return cwd, "mcp_cwd"
    if allow_missing:
        return None, None
    raise ValueError("Путь проекта не задан. Вызовите set_project_path.")


def get_project_path_status():
    saved = get_saved_project_path()
    effective, source = resolve_effective_project_root(allow_missing=True)
    export_dir = None
    if effective:
        export_dir = str(Path(effective) / settings.GP_EXPORT_SUBDIR)
    return {
        "mcp_process_cwd": os.getcwd(),
        "config_directory": str(_config_dir()),
        "saved_project_path": saved or None,
        "effective_project_path": effective,
        "effective_source": source,
        "exports_directory": export_dir,
        "needs_set_project_path": effective is None,
        "hint": (
            "Вызовите set_project_path с путём к открытому проекту в IDEA "
            "(например U:\\BDProjects\\users_scripts). CSV → <проект>/export/."
        ),
    }
