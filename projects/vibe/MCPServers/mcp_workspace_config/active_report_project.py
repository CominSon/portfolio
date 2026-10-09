"""Активный проект — указатель в папке проекта (не в MCP Servers)."""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

from mcp_workspace_config.safe_path import (
    ACTIVE_PROJECT_STORE_VERSION,
    safe_absolute,
    write_text_safe,
)

logger = logging.getLogger("report_mcp.active_project")


def _project_pointer(project_root):
    return safe_absolute(project_root) / "agent_registry" / "active_project.json"


def _mirror_path():
    base = os.environ.get("REPORT_MCP_STATE_DIR", "").strip()
    if base:
        return safe_absolute(base) / "active_report_project.json"
    return safe_absolute(os.environ.get("TEMP", os.path.expanduser("~"))) / "report_mcp_active_project.json"


def set_active_report_project(project_root, report_title=None, final_object=None):
    project_root = str(safe_absolute(project_root))
    data = {
        "version": ACTIVE_PROJECT_STORE_VERSION,
        "project_root": project_root,
        "report_title": report_title,
        "final_object": final_object,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    body = json.dumps(data, ensure_ascii=False, indent=2)
    errors = []

    try:
        write_text_safe(_mirror_path(), body)
    except PermissionError as exc:
        errors.append(str(exc))
        logger.warning("active project mirror: %s", exc)

    try:
        write_text_safe(_project_pointer(project_root), body)
    except PermissionError as exc:
        errors.append(str(exc))
        logger.warning("active project pointer: %s", exc)

    if errors and len(errors) >= 2:
        raise PermissionError("; ".join(errors))
    return data


def get_active_report_project():
    mirror = _mirror_path()
    data = None
    if mirror.is_file():
        try:
            data = json.loads(mirror.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = None
    if not data or not data.get("project_root"):
        return None
    try:
        from report_mcp_agent.src.report.manifest import load_manifest

        if not load_manifest(data["project_root"]):
            return None
    except Exception:
        return None
    return data


def clear_active_report_project():
    data = get_active_report_project()
    if data and data.get("project_root"):
        ptr = _project_pointer(data["project_root"])
        if ptr.is_file():
            try:
                ptr.unlink()
            except OSError:
                pass
    mirror = _mirror_path()
    if mirror.is_file():
        try:
            mirror.unlink()
        except OSError:
            pass
