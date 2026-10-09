"""Контекст проекта для агента."""

from pathlib import Path

from report_mcp_agent.resources import settings
from report_mcp_agent.src.report import lineage_protocol, manifest, pxf_rules, revisions


def build_context(project_root):
    data = manifest.require_manifest(project_root)
    steps = data.get("lineage_steps") or []
    open_revs = revisions.list_open_revisions(data)
    inv = data.get("inventory") or {}
    gaps = _compute_gaps(data, project_root)
    protocol = lineage_protocol.protocol_dict(in_schema=settings.GP_IN_SCHEMA)

    smd_hints = []
    for part in inv.get("participants") or []:
        if not pxf_rules.is_pxf_source_candidate(part):
            continue
        smd_hints.append({
            "object": part,
            "role": "pxf_candidate",
            "pxf_lookup_name": pxf_rules.pxf_lookup_name(part),
            "pxf_sql": pxf_rules.suggested_pxf_sql(part),
            "if_empty_or_stale": (
                "Если нет DONE в PXF или последний DONE старше {0} суток — "
                "обязательно искать процедуру сборки (p_copy* на in)."
            ).format(lineage_protocol.PXF_STALE_DAYS),
            "if_empty": pxf_rules.suggested_pcopy_hint(part),
        })

    return {
        "ok": True,
        "project_root": str(project_root),
        "report_title": data.get("report_title"),
        "final_object": data.get("final_object"),
        "status": data.get("status"),
        "lineage_protocol": protocol,
        "lineage_protocol_markdown": lineage_protocol.protocol_markdown(
            settings.GP_IN_SCHEMA
        ),
        "must_follow": (
            "Строго следуй lineage_protocol. При доработке — revision_mode "
            "(без полного перезапуска) + cascade_checklist."
        ),
        "lineage_steps_count": len(steps),
        "lineage_steps": steps,
        "inventory": inv,
        "schedule_entries": data.get("schedule_entries") or [],
        "open_revisions": open_revs,
        "extra_knowledge": data.get("extra_knowledge") or [],
        "glossary_table": data.get("glossary_table") or settings.AI_GLOSSARY_TABLE,
        "gaps": gaps,
        "smd_pxf_checklist": smd_hints[:30],
        "files_hint": {
            "root_readme": "README.md",
            "docs": data.get("doc_files") or [],
            "ddl_objects": data.get("ddl_objects") or [],
            "ddl_functions": data.get("ddl_functions") or [],
            "dml": data.get("dml_files") or [],
            "manifest": "{0}/{1}".format(
                settings.AGENT_REGISTRY_DIR, settings.MANIFEST_FILENAME
            ),
        },
        "agent_playbook": _playbook(data, gaps, open_revs, protocol),
        "rules": data.get("rules") or {},
        "sample_hint": {
            "only_schemas_ending": settings.ALLOWED_SAMPLE_SCHEMA_SUFFIX,
            "table_prefix": settings.SAMPLE_TABLE_PREFIX,
            "limit": settings.SAMPLE_ROW_LIMIT,
            "gp_tool": "run_select",
        },
        "diagram_policy": protocol["diagram_required"],
    }


def _compute_gaps(data, project_root=None):
    gaps = []
    steps = data.get("lineage_steps") or []
    if not steps:
        gaps.append({
            "code": "no_lineage",
            "message": "Нет lineage_steps. Шаг 1 протокола: writers(final_object).",
        })
    for step in steps:
        if not (step.get("reads_from") or step.get("reference_reads")):
            if (step.get("write_role") or "") != "update":
                gaps.append({
                    "code": "empty_reads",
                    "procedure": step.get("procedure"),
                    "message": "Пустой reads_from у {0}".format(step.get("procedure")),
                })
        for q in [step.get("writes_to")] + list(step.get("reads_from") or []):
            if q and "." not in q:
                gaps.append({
                    "code": "missing_schema",
                    "object": q,
                    "message": (
                        "Объект `{0}` без схемы. Определите schema (search_path в теле "
                        "функции / каталог). smd_ на in ≈ PXF; smd_ на work = промежуточная."
                    ).format(q),
                })

    inv = data.get("inventory") or {}
    participants = inv.get("participants") or []
    pxf_known = set(inv.get("pxf_sources") or [])
    pcopy_known = inv.get("pcopy_sources") or []
    pcopy_targets = set()
    for item in pcopy_known:
        if isinstance(item, dict):
            pcopy_targets.add(item.get("target"))
        else:
            pcopy_targets.add(item)

    for part in participants:
        info = pxf_rules.classify_smd_object(part)
        if info["role"] == "needs_schema":
            gaps.append({
                "code": "missing_schema",
                "object": part,
                "message": info["hint"],
            })
            continue
        if info["role"] != "pxf_candidate":
            # work.smd_* и прочие — промежуточные, PXF не требуется
            continue
        if part in pxf_known or part in pcopy_targets:
            continue
        has_sched = any(
            e.get("kind") in ("pxf", "pcopy")
            and (e.get("object") == part or e.get("target") == part)
            for e in (data.get("schedule_entries") or [])
        )
        if has_sched:
            continue
        gaps.append({
            "code": "smd_source_unclassified",
            "object": part,
            "message": (
                "Для {0} (схема in → кандидат PXF): сначала PXF table_name='{1}'. "
                "Нет записей или DONE старше {2}д → искать процедуру сборки (p_copy*)."
            ).format(
                part,
                pxf_rules.pxf_lookup_name(part),
                lineage_protocol.PXF_STALE_DAYS,
            ),
            "pxf_sql": pxf_rules.suggested_pxf_sql(part),
        })

    if not (data.get("ddl_objects") or []):
        gaps.append({"code": "no_ddl_objects", "message": "Нет sql/ddl/objects."})
    if not (data.get("ddl_functions") or []):
        gaps.append({"code": "no_ddl_functions", "message": "Нет sql/ddl/functions."})

    sources = list(inv.get("sources") or inv.get("terminal_sources") or [])
    if steps and not sources:
        gaps.append({
            "code": "sources_empty",
            "message": (
                "inventory.sources пуст. Заполните реальные источники "
                "(не промежуточные). В конце — шаг 6 recheck_sources."
            ),
        })
    # source, который сам является writes_to какого-то шага → скорее промежуточный
    writes_set = {s.get("writes_to") for s in steps if s.get("writes_to")}
    for src in sources:
        if src in writes_set:
            gaps.append({
                "code": "source_looks_intermediate",
                "object": src,
                "message": (
                    "`{0}` в sources, но на него есть writer в lineage — "
                    "это промежуточная витрина. Уберите из sources, копайте дальше "
                    "(шаг 6 recheck)."
                ).format(src),
            })

    # view в reads_from должен остаться в списке; нужен отдельный шаг procedure=view
    writes = {s.get("writes_to") for s in steps}
    procs = {s.get("procedure") for s in steps}
    for step in steps:
        for r in step.get("reads_from") or []:
            bare = (r or "").split(".")[-1].lower()
            if bare.startswith("v_") or bare.startswith("qs_mv_") or ".v_" in (r or "").lower():
                if r not in writes and r not in procs:
                    gaps.append({
                        "code": "view_step_missing",
                        "object": r,
                        "message": (
                            "View `{0}` есть в reads_from — оставьте его в списке и "
                            "добавьте lineage_step: procedure=view, writes_to=view, "
                            "reads_from=объекты из определения (как у процедуры)."
                        ).format(r),
                    })

    biz_gaps = _business_gaps(data, project_root)
    gaps.extend(biz_gaps)

    open_revs = revisions.list_open_revisions(data)
    if open_revs:
        gaps.append({
            "code": "open_revisions",
            "message": (
                "Открыто revision: {0}. Каскад ОБЯЗАТЕЛЕН: "
                "TECHNICAL.md + lineage.svg + run_order (+ BUSINESS) → resolve. "
                "Правка lineage без TECHNICAL — нарушение протокола."
            ).format(len(open_revs)),
        })

    sched = data.get("schedule_entries") or []
    if steps and not sched and not any(s.get("schedule") for s in steps):
        gaps.append({
            "code": "no_schedule",
            "message": (
                "Нет schedule_entries. Нужен schedule_label «пн–пт 06:15» "
                "из get_procedure_schedule для SVG и §5."
            ),
        })
    else:
        weak = []
        for e in sched:
            from report_mcp_agent.src.report.schedule_format import entry_schedule_label
            lab = (entry_schedule_label(e) or "").lower()
            if not lab or lab in ("daily", "weekly") or ":" not in lab:
                weak.append(e.get("object") or "?")
        if weak:
            gaps.append({
                "code": "schedule_missing_time",
                "message": (
                    "У объектов нет дня+времени (только daily/пусто): {0}. "
                    "Вызовите get_procedure_schedule → schedule_label."
                ).format(", ".join(weak[:6])),
            })
    return gaps


def _business_gaps(data, project_root):
    gaps = []
    if not project_root:
        return gaps
    path = Path(project_root) / "docs" / "BUSINESS.md"
    if not path.is_file():
        gaps.append({
            "code": "business_missing",
            "message": "Нет BUSINESS.md — обязательное детальное описание.",
        })
        return gaps
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return gaps
    low = text.lower()
    final_obj = data.get("final_object") or ""
    if final_obj and final_obj.lower() not in low and final_obj.split(".")[-1].lower() not in low:
        gaps.append({
            "code": "business_no_final",
            "message": "В BUSINESS нет детального раздела по финалу `{0}`.".format(final_obj),
        })
    stub_markers = ("_заполнить_", "| _…_", "описание: заполнить", "пока пусто")
    if any(m in low for m in stub_markers) or text.count("| поле |") < 1:
        gaps.append({
            "code": "business_shallow",
            "message": (
                "BUSINESS: нужны таблицы полей у финала и у каждого ИСТОЧНИКА "
                "(промежуточные витрины — отдельно, не называть источниками)."
            ),
        })
    sources = list(
        (data.get("inventory") or {}).get("sources")
        or (data.get("inventory") or {}).get("terminal_sources")
        or []
    )
    missing_src = []
    for t in sources[:12]:
        bare = t.split(".")[-1].lower()
        if bare and bare not in low and t.lower() not in low:
            missing_src.append(t)
    if missing_src:
        gaps.append({
            "code": "business_missing_sources",
            "message": "В BUSINESS нет раздела по источникам: {0}".format(
                ", ".join(missing_src[:6])
            ),
        })
    # источники упомянуты, но без таблицы полей рядом — грубая эвристика
    if sources and "источник" in low and text.count("| поле |") < max(2, len(sources)):
        gaps.append({
            "code": "business_sources_no_fields",
            "message": (
                "У источников в BUSINESS мало/нет таблиц полей — "
                "заполните get_columns для каждого inventory.sources."
            ),
        })
    return gaps


def _playbook(data, gaps, open_revs, protocol):
    lines = [
        "СНАЧАЛА lineage_protocol (полный текст в контексте).",
        "Финал: {0}".format(data.get("final_object")),
        "View — раскрывать; helper-функции — related_transforms, не источники.",
        "inventory.sources (не «терминальные»); промежуточные — intermediate.",
        "Шаг 6: перепроверка всех sources.",
        "View = шаг как процедура (procedure=writes_to=view). "
        "SVG сверху вниз (источники→финал); время полностью. §5 — по времени запуска.",
        "Правка lineage → ОБЯЗАТЕЛЬНО render_report_docs (TECHNICAL+SVG).",
    ]
    if open_revs:
        lines.append("РЕЖИМ ДОРАБОТКИ:")
        for r in open_revs:
            lines.append("  - [{0}] {1}".format(r.get("id"), r.get("text")))
        lines.append("Чеклист каскада (TECHNICAL обязателен):")
        for item in protocol["revision_mode"]["cascade_checklist"]:
            lines.append("  - [ ] {0}".format(item))
    elif gaps:
        critical = [
            g for g in gaps
            if g.get("code") in (
                "missing_schema",
                "empty_reads",
                "smd_source_unclassified",
                "view_step_missing",
                "sources_empty",
                "source_looks_intermediate",
                "schedule_missing_time",
                "business_shallow",
                "business_no_final",
                "business_missing_sources",
                "business_sources_no_fields",
                "open_revisions",
            )
        ]
        show = critical or gaps
        lines.append("Пробелы:")
        for g in show[:14]:
            lines.append("  - {0}: {1}".format(g.get("code"), g.get("message")))
    return lines
