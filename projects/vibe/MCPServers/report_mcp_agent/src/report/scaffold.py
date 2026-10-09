"""Создание каркаса проекта отчёта."""

import shutil
from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report import layout, manifest
from report_mcp_agent.src.report.naming import object_slug_from_table
from report_mcp_agent.src.utils.safe_path import write_text_safe


def _templates_root():
    return Path(__file__).resolve().parents[2] / "templates"


def _fill(text, mapping):
    out = text
    for key, value in mapping.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def scaffold_project(
    project_root,
    report_title,
    final_schema,
    final_table,
    adopt=False,
    object_folder=None,
):
    root = Path(project_root)
    root.mkdir(parents=True, exist_ok=True)
    # родительская папка отчёта (название отчёта) — README-заглушка по желанию
    report_parent = root.parent
    if report_parent.is_dir() and report_parent != root:
        parent_readme = report_parent / "README.md"
        if not parent_readme.is_file():
            write_text_safe(
                parent_readme,
                "# {0}\n\n"
                "Папка отчёта. Внутри — подпроекты по финальным объектам "
                "(английские имена, напр. `ukp_weeks`).\n"
                "Текущий объект: `{1}`.\n".format(
                    report_title or report_parent.name,
                    root.name,
                ),
            )

    layout.ensure_layout(root)
    manifest.registry_dir(root).mkdir(parents=True, exist_ok=True)

    existing = manifest.load_manifest(root)
    if existing and not adopt:
        return {
            "ok": True,
            "adopted": False,
            "already_exists": True,
            "project_root": str(root),
            "manifest": existing,
            "message": "Проект уже есть — resume / get_report_context.",
        }

    obj_slug = object_slug_from_table(final_table, object_folder) if final_table else root.name

    if existing and adopt:
        data = existing
        data["report_title"] = report_title or data.get("report_title")
        if final_schema:
            data["final_schema"] = final_schema
        if final_table:
            data["final_table"] = final_table
        data["final_object"] = "{0}.{1}".format(
            data.get("final_schema"), data.get("final_table")
        )
        data["glossary_table"] = data.get("glossary_table") or settings.AI_GLOSSARY_TABLE
    else:
        data = manifest.default_manifest(report_title, final_schema, final_table)

    data["object_folder"] = data.get("object_folder") or obj_slug or root.name
    data["report_folder"] = data.get("report_folder") or report_parent.name

    mapping = {
        "REPORT_TITLE": data["report_title"],
        "FINAL_SCHEMA": data["final_schema"],
        "FINAL_TABLE": data["final_table"],
        "FINAL_OBJECT": data["final_object"],
        "OBJECT_FOLDER": data["object_folder"],
        "GLOSSARY_TABLE": data.get("glossary_table") or settings.AI_GLOSSARY_TABLE,
    }

    # Корневой README
    readme_src = _templates_root() / "README.md"
    if not readme_src.is_file():
        readme_src = _templates_root() / "docs" / "README.md"
    readme_dst = root / "README.md"
    if readme_src.is_file() and (not readme_dst.is_file() or adopt):
        if not readme_dst.is_file():
            write_text_safe(readme_dst, _fill(readme_src.read_text(encoding="utf-8"), mapping))

    docs_tpl = _templates_root() / "docs"
    for name in settings.ALLOWED_DOC_FILES:
        target = root / "docs" / name
        if not target.is_file():
            src = docs_tpl / name
            if src.is_file():
                write_text_safe(target, _fill(src.read_text(encoding="utf-8"), mapping))
            else:
                write_text_safe(target, "# {0}\n".format(name))
        rel = "docs/{0}".format(name)
        if rel not in (data.get("doc_files") or []):
            data.setdefault("doc_files", []).append(rel)

    # убрать устаревший docs/README если переехали в корень
    legacy_docs_readme = root / "docs" / "README.md"
    if legacy_docs_readme.is_file() and readme_dst.is_file():
        try:
            legacy_docs_readme.unlink()
        except OSError:
            pass

    for script_name in ("create_structure_md.py", "sync_all_ddl.py"):
        py_src = _templates_root() / "python" / script_name
        py_dst = root / "python" / script_name
        if py_src.is_file() and not py_dst.is_file():
            shutil.copy2(str(py_src), str(py_dst))

    dml = root / "sql" / "dml" / "00_run_order.sql"
    if not dml.is_file():
        write_text_safe(
            dml,
            "-- Run order: {0}\n".format(data["report_title"]),
        )
        data.setdefault("dml_files", []).append("sql/dml/00_run_order.sql")

    if "README.md" not in (data.get("doc_files") or []):
        data.setdefault("doc_files", []).append("README.md")

    manifest.touch_status(data, phase="discovery", summary="Каркас создан", done=False)
    manifest.save_manifest(root, data)

    return {
        "ok": True,
        "adopted": bool(existing and adopt),
        "already_exists": False,
        "project_root": str(root),
        "manifest_path": str(manifest.manifest_path(root)),
        "manifest": data,
        "report_folder": data.get("report_folder"),
        "object_folder": data.get("object_folder"),
        "layout_note": (
            "Корень MCP = …/<Название отчёта>/<object_slug>/; "
            "DDL таблиц: sql/ddl/objects/{sources|intermediate|final}/"
        ),
        "next": (
            "get_report_context → lineage; DDL: refresh_project_ddl "
            "(objects/sources|intermediate|final); "
            "upsert_lineage_step / upsert_schedule_entry / render_report_docs."
        ),
    }
