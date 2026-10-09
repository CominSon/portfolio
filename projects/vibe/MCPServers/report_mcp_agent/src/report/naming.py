"""Имена папок проекта: report title (любой язык) + english object slug."""

import re


_STRIP_PREFIXES = (
    "qs_t_",
    "qs_mv_",
    "qs_",
    "smd_",
    "v_smd_",
    "v_",
    "t_",
    "p_",
    "f_",
)

# Подпапки sql/ddl/objects/
OBJECT_KIND_DIRS = ("sources", "intermediate", "final")


def object_slug_from_table(table_name, explicit=None):
    """
    Английский slug подпапки объекта из имени финальной таблицы.
    qs_t_ukp_weeks → ukp_weeks; smd_foo → foo.
    """
    if explicit and str(explicit).strip():
        return _ascii_slug(explicit)
    name = (table_name or "").strip()
    if "." in name:
        name = name.split(".")[-1]
    low = name.lower()
    for pref in _STRIP_PREFIXES:
        if low.startswith(pref):
            name = name[len(pref) :]
            break
    return _ascii_slug(name) or "object"


def _ascii_slug(text):
    text = (text or "").strip().lower()
    text = re.sub(r"[^a-z0-9_\-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_-")
    return text


def report_folder_name(report_title, folder_name=None):
    """Верхняя папка отчёта — как задал пользователь (можно кириллица)."""
    name = (folder_name or report_title or "report").strip()
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "report"


def classify_object_kind(qualified, data):
    """
    sources | intermediate | final — куда класть DDL таблицы/view.
    """
    q = (qualified or "").strip()
    inv = data.get("inventory") or {}
    final_obj = (data.get("final_object") or "").strip()
    sources = set(inv.get("sources") or inv.get("terminal_sources") or [])
    intermediate = set(inv.get("intermediate") or [])
    pxf = set(inv.get("pxf_sources") or [])

    if final_obj and q == final_obj:
        return "final"
    if q in sources or q in pxf:
        return "sources"
    if q in intermediate:
        return "intermediate"

    bare = q.split(".")[-1].lower()
    sch = q.split(".")[0].lower() if "." in q else ""
    if bare.startswith("smd_") and (sch.endswith("_in") or sch == "in"):
        return "sources"

    writes = {
        (s.get("writes_to") or "").strip()
        for s in (data.get("lineage_steps") or [])
    }
    if q in writes:
        return "intermediate"
    return "intermediate"
