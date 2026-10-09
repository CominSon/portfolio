"""Корень git-проекта. Конфиг: bitbucket_mcp_agent/bb_mcp_config/."""

import json
import os
import subprocess
from pathlib import Path

from bitbucket_mcp_agent.resources import settings
from bitbucket_mcp_agent.src.utils.safe_path import package_root, safe_absolute

_IDE_ENV_KEYS = (
    "MCP_PROJECT_PATH",
    "BB_PROJECT_PATH",
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


def get_saved_project_path():
    return (load_profile().get("project_path") or "").strip()


def set_saved_project_path(path, note=None):
    path = _normalize_path(path)
    data = load_profile()
    data["project_path"] = path
    if note:
        data["note"] = note
    result = save_profile(data)
    result["project_path"] = path
    result["config_directory"] = str(_config_dir())
    try:
        from mcp_workspace_config.project_store import save_shared_project
        root = _git_toplevel(path)
        shared = save_shared_project(root, source="bb_mcp", note=note)
        result["shared_config_path"] = shared.get("shared_config_path")
        result["project_path"] = root
        data["project_path"] = root
        save_profile(data)
    except Exception:
        pass
    return result


def _normalize_path(path_str):
    path_str = (path_str or "").strip().strip('"').strip("'")
    if not path_str:
        raise ValueError("Путь к проекту пустой")
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(os.getcwd()) / path
    return str(safe_absolute(path))


def _git_toplevel(path):
    proc = subprocess.run(
        ["git", "-C", path, "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if proc.returncode != 0:
        raise ValueError(
            "Не git-репозиторий: {0}. {1}".format(path, proc.stderr.strip())
        )
    return proc.stdout.strip()


def validate_and_resolve_project_path(path_str):
    normalized = _normalize_path(path_str)
    root = _git_toplevel(normalized)
    return {"project_path": root, "normalized_from": normalized}


def _path_from_env():
    for key in _IDE_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            try:
                return _git_toplevel(_normalize_path(value)), "env:{0}".format(key)
            except ValueError:
                continue
    return None, None


def _path_from_mcp_cwd():
    try:
        return _git_toplevel(os.getcwd()), "mcp_cwd"
    except ValueError:
        return None, None


def get_project_path_status():
    saved = get_saved_project_path()
    effective, source = resolve_effective_project_root(allow_missing=True)
    return {
        "mcp_process_cwd": os.getcwd(),
        "config_directory": str(_config_dir()),
        "saved_project_path": saved or None,
        "effective_project_path": effective,
        "effective_source": source,
        "needs_set_project_path": effective is None,
        "hint": "Вызовите set_project_path с путём к открытому клону.",
    }


def _mcp_servers_root():
    p = Path(__file__).absolute()
    return p.parents[3]


def _path_from_shared_or_gp():
    try:
        from mcp_workspace_config.project_store import get_shared_project_path
        shared = get_shared_project_path()
        if shared:
            return _git_toplevel(shared), "shared"
    except Exception:
        pass

    try:
        mcp_root = _mcp_servers_root()
    except IndexError:
        return None, None

    for rel in (
        "gp_mcp_agent/src/gp_mcp_config/project_profile.json",
        "gp_mcp_agent/gp_mcp_config/project_profile.json",
        "mcp_workspace_config/project_path.json",
    ):
        profile = mcp_root / rel
        if not profile.is_file():
            continue
        try:
            with profile.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            project_path = (data.get("project_path") or "").strip()
            if project_path:
                return _git_toplevel(project_path), "gp_profile"
        except (ValueError, OSError):
            continue
    return None, None


def _auto_save_if_from_env(path, source):
    if not path or get_saved_project_path():
        return False
    try:
        set_saved_project_path(path, note="auto:{0}".format(source))
        return True
    except ValueError:
        return False


def resolve_effective_project_root(allow_missing=False):
    saved = get_saved_project_path()
    if saved:
        try:
            return _git_toplevel(saved), "saved"
        except ValueError:
            pass

    shared_root, shared_src = _path_from_shared_or_gp()
    if shared_root:
        return shared_root, shared_src

    env_root, env_src = _path_from_env()
    if env_root:
        auto = _auto_save_if_from_env(env_root, env_src)
        source = "{0}:auto_saved".format(env_src) if auto else env_src
        return env_root, source
    mcp_root, mcp_src = _path_from_mcp_cwd()
    if mcp_root:
        return mcp_root, mcp_src
    if allow_missing:
        return None, None
    raise ValueError(
        "Корень git-проекта не задан. Вызовите set_project_path."
    )


def get_effective_cwd():
    root, _ = resolve_effective_project_root(allow_missing=False)
    return root
