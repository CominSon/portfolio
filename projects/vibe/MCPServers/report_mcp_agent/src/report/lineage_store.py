"""Upsert шагов lineage, inventory, schedule_entries."""

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report import manifest
from report_mcp_agent.src.report.pxf_rules import pxf_lookup_name


def _assert_qualified_schemas(*qualified_list):
    """Требуем schema.object. work.smd_* допустим (промежуточная, не PXF)."""
    errors = []
    for q in qualified_list:
        if not q:
            continue
        if "." not in q:
            errors.append(
                "Объект `{0}` без схемы. Укажите schema.object "
                "(search_path в теле функции / каталог). "
                "smd_ на {1} ≈ PXF; smd_ на work = промежуточная."
                .format(q, settings.GP_IN_SCHEMA)
            )
    if errors:
        raise ValueError("; ".join(errors))


def upsert_lineage_step(
    project_root,
    procedure,
    writes_to,
    reads_from=None,
    reference_reads=None,
    write_role=None,
    branch_role=None,
    notes=None,
    schedule=None,
):
    data = manifest.require_manifest(project_root)
    procedure = (procedure or "").strip()
    writes_to = (writes_to or "").strip()
    if not procedure or not writes_to:
        raise ValueError("procedure и writes_to обязательны")

    reads = list(reads_from) if reads_from is not None else None
    refs = list(reference_reads) if reference_reads is not None else None
    check = [writes_to]
    if reads is not None:
        check.extend(reads)
    if refs is not None:
        check.extend(refs)
    _assert_qualified_schemas(*check)

    steps = data.setdefault("lineage_steps", [])
    existing = None
    for step in steps:
        if step.get("procedure") == procedure and step.get("writes_to") == writes_to:
            existing = step
            break

    if existing is None:
        existing = {
            "order": len(steps) + 1,
            "procedure": procedure,
            "writes_to": writes_to,
        }
        steps.append(existing)
        created = True
    else:
        created = False

    if reads is not None:
        existing["reads_from"] = reads
    else:
        existing.setdefault("reads_from", [])
    if refs is not None:
        existing["reference_reads"] = refs
    if write_role:
        existing["write_role"] = write_role
    if branch_role:
        existing["branch_role"] = branch_role
    if notes is not None:
        existing["notes"] = notes
    if schedule is not None:
        existing["schedule"] = schedule
        upsert_schedule_entry_in_data(
            data,
            kind="procedure",
            object_name=procedure,
            target=writes_to,
            summary=schedule if isinstance(schedule, dict) else {"note": schedule},
        )

    _refresh_participants(data)
    manifest.touch_status(
        data,
        phase="lineage",
        summary="upsert {0} → {1}".format(procedure, writes_to),
    )
    manifest.save_manifest(project_root, data)
    return {"ok": True, "created": created, "step": existing, "steps_count": len(steps)}


def upsert_schedule_entry_in_data(
    data,
    kind,
    object_name,
    target=None,
    summary=None,
    last_success=None,
    cadence=None,
    note=None,
    pxf_table_name=None,
    schedule_label=None,
):
    """Одна запись на (kind, object) — без дублей из-за разного target."""
    entries = data.setdefault("schedule_entries", [])
    kind = (kind or "procedure").strip()
    object_name = (object_name or "").strip()
    key_target = (target or "").strip()
    existing = None
    for e in entries:
        if e.get("kind") == kind and e.get("object") == object_name:
            existing = e
            break
    if existing is None:
        existing = {"kind": kind, "object": object_name}
        entries.append(existing)
    # target — справочно, не ключ; не плодим вторую строку
    if key_target:
        existing["target"] = key_target
    if summary is not None:
        existing["summary"] = summary
        if isinstance(summary, dict) and summary.get("schedule_label"):
            existing["schedule_label"] = summary["schedule_label"]
    if schedule_label is not None:
        existing["schedule_label"] = schedule_label
    if last_success is not None:
        existing["last_success"] = last_success
    if cadence is not None:
        existing["cadence"] = cadence
    if note is not None:
        existing["note"] = note
    if kind == "pxf":
        existing["pxf_table_name"] = pxf_table_name or pxf_lookup_name(
            object_name or key_target
        )
    return existing


def upsert_schedule_entry(project_root, **kwargs):
    data = manifest.require_manifest(project_root)
    object_name = kwargs.get("object_name") or kwargs.get("object")
    entry = upsert_schedule_entry_in_data(
        data,
        kind=kwargs.get("kind"),
        object_name=object_name,
        target=kwargs.get("target"),
        summary=kwargs.get("summary"),
        last_success=kwargs.get("last_success"),
        cadence=kwargs.get("cadence"),
        note=kwargs.get("note"),
        pxf_table_name=kwargs.get("pxf_table_name"),
        schedule_label=kwargs.get("schedule_label"),
    )
    inv = data.setdefault("inventory", {})
    if kwargs.get("kind") == "pxf":
        smd = object_name or kwargs.get("target")
        if smd:
            lst = inv.setdefault("pxf_sources", [])
            if smd not in lst:
                lst.append(smd)
    if kwargs.get("kind") == "pcopy":
        item = {
            "procedure": object_name,
            "target": kwargs.get("target"),
            "schedule": kwargs.get("summary") or kwargs.get("last_success"),
        }
        lst = inv.setdefault("pcopy_sources", [])
        if item not in lst:
            lst.append(item)
    manifest.save_manifest(project_root, data)
    return {"ok": True, "entry": entry, "schedule_entries": data.get("schedule_entries")}


def _refresh_participants(data):
    inv = data.setdefault("inventory", {})
    parts = set(inv.get("participants") or [])
    if data.get("final_object"):
        parts.add(data["final_object"])
    for step in data.get("lineage_steps") or []:
        if step.get("writes_to"):
            parts.add(step["writes_to"])
        for src in step.get("reads_from") or []:
            parts.add(src)
        for src in step.get("reference_reads") or []:
            parts.add(src)
        proc = step.get("procedure")
        if proc:
            parts.add(proc)
    inv["participants"] = sorted(parts)


def update_inventory(
    project_root,
    sources=None,
    terminal_sources=None,
    builders=None,
    loaders=None,
    intermediate=None,
    pxf_sources=None,
    pcopy_sources=None,
    related_transforms=None,
):
    """sources — канон; terminal_sources принимается как алиас (legacy)."""
    data = manifest.require_manifest(project_root)
    inv = data.setdefault("inventory", {})
    src = sources if sources is not None else terminal_sources
    if src is not None:
        inv["sources"] = list(src)
        inv["terminal_sources"] = list(src)  # совместимость со старыми проектами
    if builders is not None:
        inv["builders"] = list(builders)
    if loaders is not None:
        inv["loaders"] = list(loaders)
    if intermediate is not None:
        inv["intermediate"] = list(intermediate)
    if pxf_sources is not None:
        inv["pxf_sources"] = list(pxf_sources)
    if pcopy_sources is not None:
        inv["pcopy_sources"] = list(pcopy_sources)
    if related_transforms is not None:
        inv["related_transforms"] = list(related_transforms)
    _refresh_participants(data)
    manifest.save_manifest(project_root, data)
    return {"ok": True, "inventory": inv}


def inventory_sources(data):
    inv = data.get("inventory") or {}
    return list(inv.get("sources") or inv.get("terminal_sources") or [])


def set_extra_knowledge(project_root, items, replace=False):
    data = manifest.require_manifest(project_root)
    if replace:
        data["extra_knowledge"] = list(items or [])
    else:
        existing = {x.get("id"): x for x in (data.get("extra_knowledge") or []) if x.get("id")}
        for item in items or []:
            iid = item.get("id") or item.get("title")
            if not iid:
                continue
            item = dict(item)
            item["id"] = iid
            existing[iid] = item
        data["extra_knowledge"] = list(existing.values())
    manifest.save_manifest(project_root, data)
    return {"ok": True, "extra_knowledge": data["extra_knowledge"]}


def remove_lineage_objects(project_root, objects=None, procedures=None):
    """
    Удалить лишние объекты/процедуры из lineage (для доработок).
    objects — qualified tables; procedures — qualified procs.
    """
    from report_mcp_agent.src.report.lineage_protocol import protocol_dict

    data = manifest.require_manifest(project_root)
    objects = set(o.strip() for o in (objects or []) if o and str(o).strip())
    procedures = set(p.strip() for p in (procedures or []) if p and str(p).strip())
    if not objects and not procedures:
        raise ValueError("Укажите objects и/или procedures для удаления")

    steps = data.get("lineage_steps") or []
    kept = []
    removed_steps = []
    for step in steps:
        proc = step.get("procedure") or ""
        wt = step.get("writes_to") or ""
        drop = proc in procedures or wt in objects
        if not drop:
            # вычистить reads
            reads = [r for r in (step.get("reads_from") or []) if r not in objects]
            refs = [r for r in (step.get("reference_reads") or []) if r not in objects]
            step["reads_from"] = reads
            if "reference_reads" in step:
                step["reference_reads"] = refs
            kept.append(step)
        else:
            removed_steps.append(step)
    for i, step in enumerate(kept, 1):
        step["order"] = i
    data["lineage_steps"] = kept

    entries = data.get("schedule_entries") or []
    data["schedule_entries"] = [
        e for e in entries
        if (e.get("object") not in objects and e.get("object") not in procedures
            and e.get("target") not in objects)
    ]

    inv = data.setdefault("inventory", {})
    for key in (
        "sources",
        "terminal_sources",
        "builders",
        "loaders",
        "intermediate",
        "related_transforms",
        "pxf_sources",
    ):
        if key in inv and isinstance(inv[key], list):
            inv[key] = [x for x in inv[key] if x not in objects]
    if "pcopy_sources" in inv:
        cleaned = []
        for item in inv["pcopy_sources"]:
            if isinstance(item, dict):
                if item.get("target") in objects or item.get("procedure") in procedures:
                    continue
            elif item in objects:
                continue
            cleaned.append(item)
        inv["pcopy_sources"] = cleaned

    # ddl lists
    for key in ("ddl_objects", "ddl_functions"):
        lst = data.get(key) or []
        data[key] = [
            rel for rel in lst
            if not any(o.replace(".", ".") in rel for o in objects | procedures)
        ]

    _refresh_participants(data)
    # убрать удалённые из participants
    inv["participants"] = [
        p for p in (inv.get("participants") or [])
        if p not in objects and p not in procedures
    ]
    if data.get("final_object") and data["final_object"] not in inv["participants"]:
        inv["participants"].append(data["final_object"])
        inv["participants"] = sorted(set(inv["participants"]))

    manifest.touch_status(
        data,
        phase="revision",
        summary="removed {0} steps, objects={1}".format(
            len(removed_steps), len(objects | procedures)
        ),
        done=False,
    )
    manifest.save_manifest(project_root, data)
    return {
        "ok": True,
        "removed_steps": removed_steps,
        "steps_count": len(kept),
        "cascade_checklist": protocol_dict()["revision_mode"]["cascade_checklist"],
        "next": (
            "Каскад: render_report_docs → почистить BUSINESS → DDL при необходимости → "
            "resolve_report_revision."
        ),
    }
