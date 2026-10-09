"""Проверка полноты проекта отчёта."""

from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report import manifest, revisions


def validate_project(project_root):
    data = manifest.require_manifest(project_root)
    root = Path(project_root)
    errors = []
    warnings = []

    if not (root / "README.md").is_file():
        errors.append("Нет корневого README.md")

    for name in settings.ALLOWED_DOC_FILES:
        path = root / "docs" / name
        if not path.is_file():
            errors.append("Нет docs/{0}".format(name))
        elif path.stat().st_size < 40:
            warnings.append("docs/{0} почти пустой".format(name))

    if not (root / "docs" / "lineage.svg").is_file():
        warnings.append("Нет docs/lineage.svg — вызовите render_report_docs")

    dml = root / "sql" / "dml" / "00_run_order.sql"
    if not dml.is_file():
        errors.append("Нет sql/dml/00_run_order.sql")

    if not manifest.manifest_path(root).is_file():
        errors.append(
            "Manifest должен быть в {0}/".format(settings.AGENT_REGISTRY_DIR)
        )

    if (root / settings.MANIFEST_FILENAME).is_file():
        warnings.append(
            "Устаревший {0} в корне — перенесите в {1}/".format(
                settings.MANIFEST_FILENAME, settings.AGENT_REGISTRY_DIR
            )
        )

    steps = data.get("lineage_steps") or []
    if not steps:
        errors.append("lineage_steps пуст")

    for step in steps:
        for q in [step.get("writes_to")] + list(step.get("reads_from") or []):
            if q and "." not in str(q):
                errors.append(
                    "Объект `{0}` без схемы (smd_ на in ≈ PXF; smd_ на work = промежуточная)"
                    .format(q)
                )

    if not (data.get("ddl_objects") or []):
        warnings.append("ddl_objects пуст")
    if not (data.get("ddl_functions") or []):
        warnings.append("ddl_functions пуст")

    if not (data.get("schedule_entries") or []) and not any(
        s.get("schedule") for s in steps
    ):
        warnings.append("Нет schedule_entries (процедуры/PXF) для TECHNICAL §5")

    open_revs = revisions.list_open_revisions(data)
    if open_revs:
        errors.append(
            "Открыты revision: {0}".format(", ".join(r.get("id") for r in open_revs))
        )

    # BUSINESS глубина
    biz = root / "docs" / "BUSINESS.md"
    if biz.is_file():
        btxt = biz.read_text(encoding="utf-8").lower()
        if "| поле |" not in btxt and "|поле|" not in btxt.replace(" ", ""):
            errors.append("BUSINESS без таблиц полей (обязательно для финала и источников)")
        stubs = ("_заполнить_", "| _…_", "описание: заполнить")
        if any(s in btxt for s in stubs):
            warnings.append("BUSINESS содержит заглушки — дописать детально")
        final_obj = (data.get("final_object") or "").lower()
        if final_obj and final_obj not in btxt and final_obj.split(".")[-1] not in btxt:
            errors.append("BUSINESS не описывает финальный объект")

    for bad in settings.FORBIDDEN_DOC_NAMES:
        if (root / "docs" / bad).is_file():
            warnings.append("Запрещённый файл docs/{0}".format(bad))

    ok = not errors
    if ok:
        manifest.touch_status(data, phase="done", summary="validate OK", done=True)
        manifest.save_manifest(project_root, data)

    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "steps_count": len(steps),
        "open_revisions": len(open_revs),
        "final_object": data.get("final_object"),
        "manifest_path": str(manifest.manifest_path(root)),
    }
