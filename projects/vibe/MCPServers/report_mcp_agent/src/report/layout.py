"""Макет каталогов проекта отчёта (object-root)."""

from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report.naming import OBJECT_KIND_DIRS


LAYOUT_DIRS = (
    "docs",
    "sql/ddl/objects/sources",
    "sql/ddl/objects/intermediate",
    "sql/ddl/objects/final",
    "sql/ddl/functions",
    "sql/dml",
    "python",
    settings.AGENT_REGISTRY_DIR,
)


def ensure_layout(project_root):
    root = Path(project_root)
    created = []
    for rel in LAYOUT_DIRS:
        path = root / rel
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            created.append(rel)
    # legacy flat objects/ — оставить, если есть; новые пишем в подпапки
    legacy = root / "sql" / "ddl" / "objects"
    if not legacy.is_dir():
        legacy.mkdir(parents=True, exist_ok=True)
    return {"root": str(root), "created_dirs": created}


def objects_kind_dir(project_root, kind):
    kind = kind if kind in OBJECT_KIND_DIRS else "intermediate"
    return Path(project_root) / "sql" / "ddl" / "objects" / kind


def relative_allowed(rel_path):
    rel = (rel_path or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        return False
    if rel == "README.md" or rel == "PROJECT_STRUCTURE.md":
        return True
    if rel.startswith(settings.AGENT_REGISTRY_DIR + "/"):
        return True
    allowed_prefixes = ("docs/", "sql/", "python/")
    if rel in (
        "docs/TECHNICAL.md",
        "docs/BUSINESS.md",
        "docs/lineage.svg",
        "sql/dml/00_run_order.sql",
        "python/create_structure_md.py",
        "python/sync_all_ddl.py",
    ):
        return True
    for prefix in allowed_prefixes:
        if rel.startswith(prefix):
            name = Path(rel).name
            if name in settings.FORBIDDEN_DOC_NAMES:
                return False
            return True
    return False
