"""
Канонический протокол пирамиды lineage для LLM.

Всегда отдаётся в get_report_context и кратко в MCP instructions.
Доработка (revision) — та же логика на дельте, без полного перезапуска.
"""

PROTOCOL_ID = "ubhq_lineage_pyramid_v4"
PXF_STALE_DAYS = 10


def protocol_dict(in_schema="s_grnplm_ld_blago_ubhq_in", stale_days=None):
    stale = PXF_STALE_DAYS if stale_days is None else stale_days
    return {
        "id": PROTOCOL_ID,
        "title": "Пирамида lineage UBHQ (строго)",
        "pxf_stale_days": stale,
        "steps": [
            {
                "n": 1,
                "name": "writers_for_target",
                "text": (
                    "От текущего целевого объекта (старт = final_object): "
                    "get_link_object(object_name=имя таблицы) → сырой список как f_get_link_object. "
                    "Для каждого кандидата — get_function / get_view_ddl; агент сам решает связь. "
                    "Приоритет writers: INSERT/TRUNCATE+INSERT; UPDATE тоже в цепочку. "
                    "НЕ писать в reads_from: helper-функции преобразования значений "
                    "(их — в inventory.related_transforms). "
                    "VIEW в reads_from родителя ОСТАВЛЯТЬ как имя view (не подменять "
                    "сразу его внутренними таблицами) — дальше отдельный шаг по view (2b)."
                ),
            },
            {
                "n": 2,
                "name": "analyze_procedure_reads",
                "text": (
                    "Для каждой writer-процедуры: get_function(for_lineage=true). "
                    "Только ФИЗИЧЕСКИЕ reads (FROM/JOIN, CTE→физика, temp→underlying). "
                    "Побочные writes в другие таблицы — не в пирамиду. "
                    "Схема обязательна (search_path / каталог). "
                    "smd_ сам по себе ≠ PXF — смотрите схему. "
                    "Если среди reads есть VIEW — имя view остаётся в reads_from; "
                    "отдельный lineage_step по этому view (шаг 2b)."
                ),
            },
            {
                "n": "2b",
                "name": "analyze_view_like_procedure",
                "text": (
                    "VIEW = тот же тип шага, что и процедура (не «раскрыть и выкинуть»). "
                    "В lineage_steps: procedure=<имя view>, writes_to=<то же имя view>, "
                    "reads_from=<объекты из определения view>. "
                    "Три поля: имя view | финальный объект (= view) | источники. "
                    "У процедуры: имя процедуры | пишет в (таблица/view) | источники. "
                    "Дальше каждый reads_from view снова идёт в пирамиду (шаг 1–2b). "
                    "Нельзя: убрать view из списков и подставить только его внутренности "
                    "в reads_from родителя."
                ),
            },
            {
                "n": 3,
                "name": "recurse_sources",
                "text": (
                    "Каждый объект из reads_from (таблица или view) — новый целевой: "
                    "таблица → writers; view → шаг 2b. "
                    "Промежуточные витрины — узлы цепочки, не inventory.sources; "
                    "копать до реальных источников (in.smd_* / PXF / без writer)."
                ),
            },
            {
                "n": 4,
                "name": "sources_stop",
                "text": (
                    "Стоп по ветке, когда нет writer'а (или сработал шаг 5 для in.smd_*). "
                    "Фиксировать в inventory.sources (не называть «терминальными»). "
                    "Промежуточные витрины — inventory.intermediate."
                ),
            },
            {
                "n": 5,
                "name": "smd_pxf_or_pcopy",
                "text": (
                    "in.`{in_sch}`.smd_* ≈ PXF: logs_pxf table_name без smd_ точно; "
                    "пусто или DONE >{stale}д → процедура сборки (p_copy*). "
                    "work.smd_* = промежуточная, не PXF. v_smd* на in — смотреть определение."
                ).format(in_sch=in_schema, stale=stale),
            },
            {
                "n": 6,
                "name": "recheck_sources",
                "text": (
                    "ОБЯЗАТЕЛЬНО в конце (и перед validate): ещё раз пройти inventory.sources "
                    "и все листья lineage. Для каждого: это правда источник, а не промежуточная "
                    "таблица или view без своего lineage_step? Если сомнение — разбор. "
                    "Нельзя с первого прохода оставить промежуточный объект в sources."
                ),
            },
        ],
        "revision_mode": {
            "full_rebuild": False,
            "text": (
                "Доработка НЕ полный перезапуск. Дельта → remove_lineage_objects → "
                "ОБЯЗАТЕЛЬНО каскад: TECHNICAL.md + lineage.svg + run_order + BUSINESS "
                "(где затронуто) + DDL при необходимости → resolve. "
                "Любое изменение lineage/schedule БЕЗ обновления TECHNICAL — нарушение протокола."
            ),
            "cascade_checklist": [
                "remove_lineage_objects для лишнего",
                "upsert lineage_steps + schedule_entries (одна запись на объект)",
                "ОБЯЗАТЕЛЬНО render_report_docs → TECHNICAL.md + lineage.svg + run_order",
                "BUSINESS: источники (поля!) + промежуточные витрины отдельно",
                "шаг 6 recheck_sources",
                "resolve_report_revision",
            ],
        },
        "business_required": (
            "BUSINESS.md: (1) финал — смысл + поля; "
            "(2) ИСТОЧНИКИ — каждый из inventory.sources: смысл + таблица полей "
            "(get_columns / семплы); "
            "(3) промежуточные витрины — можно кратко, НЕ называть источниками. "
            "Заглушки без полей у источников — не принимать."
        ),
        "diagram_required": (
            "docs/lineage.svg: СВЕРХУ ВНИЗ — стартовые источники сверху, финал снизу. "
            "На схеме полностью видно день(ru)+время (пн–пт 06:15), без обрезки. "
            "Порядок шагов на схеме и в §5 — по времени запуска."
        ),
        "schedule_required": (
            "TECHNICAL §5: ОДНА таблица «Порядок запуска» (PXF + процедуры + p_copy), "
            "колонки: # | Объект | Тип | Расписание (день+время) | Примечание. "
            "Без колонки «целевая таблица». Одна строка на объект (без дублей). "
            "Сортировка по типичному времени запуска. "
            "Отдельно §5.2 — объекты без записей в логах."
        ),
        "project_layout": (
            "Структура: `<Название отчёта>/<object_slug>/` — "
            "верхняя папка = название отчёта (можно кириллица); "
            "подпапка на английском из финального объекта (qs_t_ukp_weeks → ukp_weeks) "
            "или object_folder / просьба пользователя. MCP project_root = object_slug. "
            "DDL: sql/ddl/objects/sources|intermediate|final/ + sql/ddl/functions/. "
            "Обновить: refresh_project_ddl / python/sync_all_ddl.py; "
            "карту файлов — python/create_structure_md.py."
        ),
        "hard_rules": [
            "папки: <Отчёт>/<object_slug>/; DDL objects/{sources,intermediate,final}/",
            "view = шаг как процедура: procedure=view, writes_to=view, reads_from=…; "
            "view остаётся в списках родителя",
            "helper/transform-функции — related_transforms, не reads_from/источники",
            "источники = inventory.sources (не «терминальные»)",
            "промежуточные витрины ≠ источники",
            "шаг 6: финальная перепроверка sources",
            "SVG сверху вниз (источники сверху → финал снизу); время полностью видно",
            "порядок сборки/§5 — по времени запуска",
            "любая правка lineage → обязательно обновить TECHNICAL (+ SVG)",
            "§5: одна таблица по порядку запуска, без дублей и без «целевой таблицы»",
            "in.smd_* ≈ PXF; work.smd_* = промежуточная",
            "для in.smd_*: PXF пусто или >{0}д → процедура сборки".format(stale),
        ],
    }


def protocol_markdown(in_schema="s_grnplm_ld_blago_ubhq_in"):
    p = protocol_dict(in_schema=in_schema)
    lines = [
        "# {0}".format(p["title"]),
        "",
        "id: {0}".format(p["id"]),
        "",
    ]
    for step in p["steps"]:
        lines.append("## {0}. {1}".format(step["n"], step["name"]))
        lines.append("")
        lines.append(step["text"])
        lines.append("")
    lines.append("## revision_mode")
    lines.append("")
    lines.append(p["revision_mode"]["text"])
    lines.append("")
    for item in p["revision_mode"]["cascade_checklist"]:
        lines.append("- [ ] {0}".format(item))
    lines.append("")
    lines.append("## project_layout")
    lines.append("")
    lines.append(p["project_layout"])
    lines.append("")
    lines.append("## business / diagram / schedule")
    lines.append("")
    lines.append(p["business_required"])
    lines.append("")
    lines.append(p["diagram_required"])
    lines.append("")
    lines.append(p["schedule_required"])
    lines.append("")
    lines.append("## hard_rules")
    lines.append("")
    for r in p["hard_rules"]:
        lines.append("- {0}".format(r))
    lines.append("")
    return "\n".join(lines)


def protocol_instructions_block(in_schema="s_grnplm_ld_blago_ubhq_in"):
    return (
        "ОБЯЗАТЕЛЬНЫЙ протокол lineage ({0}) — полный текст в get_report_context"
        "['lineage_protocol']. Кратко:\n"
        "1) get_link_object → сырой список; get_function/get_view; агент отбирает writers;\n"
        "2) физические reads; VIEW = отдельный шаг как процедура "
        "(procedure=view, writes_to=view, reads_from=…), имя view остаётся у родителя;\n"
        "2+) helper-преобразования — related_transforms, не источники;\n"
        "3) рекурсия; промежуточные ≠ sources;\n"
        "4) inventory.sources (не «терминальные»);\n"
        "5) in.smd_* ≈ PXF; work.smd_* = промежуточная;\n"
        "6) финальная перепроверка sources.\n"
        "Структура: <Отчёт>/<object_slug>/; DDL objects/sources|intermediate|final/.\n"
        "SVG: сверху вниз; время полностью. §5 по порядку запуска. Правка → TECHNICAL+SVG.\n"
        "Перед работой: get_report_context → lineage_protocol."
    ).format(PROTOCOL_ID)
