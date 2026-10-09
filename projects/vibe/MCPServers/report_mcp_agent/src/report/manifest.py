"""REPORT_MANIFEST.json — состояние проекта (лежит в agent_registry/)."""

import json
import shutil
from datetime import datetime
from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.utils.safe_path import safe_absolute, write_text_safe


def _now():
    return datetime.now().isoformat(timespec="seconds")


def default_manifest(report_title, final_schema, final_table):
    final_object = "{0}.{1}".format(final_schema, final_table)
    return {
        "version": settings.MANIFEST_VERSION,
        "template_version": "3.1",
        "report_title": report_title,
        "final_schema": final_schema,
        "final_table": final_table,
        "final_object": final_object,
        "object_folder": "",
        "report_folder": "",
        "created_at": _now(),
        "updated_at": _now(),
        "lineage_steps": [],
        "inventory": {
            "sources": [],
            "terminal_sources": [],  # legacy alias → sources
            "builders": [],
            "loaders": [],
            "intermediate": [],
            "related_transforms": [],
            "participants": [final_object],
            "pxf_sources": [],
            "pcopy_sources": [],
        },
        "schedule_entries": [],
        "ddl_objects": [],
        "ddl_functions": [],
        "dml_files": [],
        "doc_files": [],
        "revisions": [],
        "extra_knowledge": [],
        "agent_notes": [],
        "glossary_table": settings.AI_GLOSSARY_TABLE,
        "status": {
            "phase": "discovery",
            "done": False,
            "last_summary": "",
        },
        "rules": {
            "docs_only": list(settings.ALLOWED_DOC_FILES),
            "no_ext_samples": True,
            "sample_schema_suffix": settings.ALLOWED_SAMPLE_SCHEMA_SUFFIX,
            "sample_table_prefix": settings.SAMPLE_TABLE_PREFIX,
            "sample_row_limit": settings.SAMPLE_ROW_LIMIT,
            "pxf_exact_name_without_smd": True,
            "pcopy_if_no_pxf": True,
            "smd_on_in_is_pxf_candidate": True,
            "smd_off_in_is_intermediate": True,
            "continue_no_bfs_expand": True,
            "cascade_revision_files": True,
        },
    }


def registry_dir(project_root):
    return safe_absolute(project_root) / settings.AGENT_REGISTRY_DIR


def manifest_path(project_root):
    return registry_dir(project_root) / settings.MANIFEST_FILENAME


def legacy_manifest_path(project_root):
    return safe_absolute(project_root) / settings.MANIFEST_FILENAME


def _migrate_legacy_json(project_root):
    """Перенести REPORT_MANIFEST / structure_summary из корня в agent_registry."""
    reg = registry_dir(project_root)
    reg.mkdir(parents=True, exist_ok=True)
    root = safe_absolute(project_root)
    for name in (settings.MANIFEST_FILENAME, settings.STRUCTURE_SUMMARY_FILENAME):
        src = root / name
        dst = reg / name
        if src.is_file() and not dst.is_file():
            try:
                shutil.move(str(src), str(dst))
            except OSError:
                try:
                    write_text_safe(dst, src.read_text(encoding="utf-8"))
                    src.unlink()
                except OSError:
                    pass


def load_manifest(project_root):
    _migrate_legacy_json(project_root)
    path = manifest_path(project_root)
    if not path.is_file():
        legacy = legacy_manifest_path(project_root)
        if legacy.is_file():
            _migrate_legacy_json(project_root)
            path = manifest_path(project_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def save_manifest(project_root, data):
    data = dict(data or {})
    data["updated_at"] = _now()
    path = manifest_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_safe(path, json.dumps(data, ensure_ascii=False, indent=2))
    # убрать устаревшую копию в корне, если появилась
    legacy = legacy_manifest_path(project_root)
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass
    return data


def require_manifest(project_root):
    data = load_manifest(project_root)
    if not data:
        raise ValueError(
            "Нет {0}/{1}. Сначала start_report_project или resume_report_project.".format(
                settings.AGENT_REGISTRY_DIR, settings.MANIFEST_FILENAME
            )
        )
    return data


def touch_status(data, phase=None, summary=None, done=None):
    st = data.setdefault("status", {})
    if phase is not None:
        st["phase"] = phase
    if summary is not None:
        st["last_summary"] = summary
    if done is not None:
        st["done"] = bool(done)
    return data
