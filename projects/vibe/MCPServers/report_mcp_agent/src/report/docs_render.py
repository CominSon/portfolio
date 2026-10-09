"""Генерация TECHNICAL / BUSINESS / DML / SVG."""

from pathlib import Path

from report_mcp_agent.src.report import diagram_svg, lineage_store, manifest
from report_mcp_agent.src.report.schedule_format import format_run_order_section
from report_mcp_agent.src.utils.safe_path import write_text_safe


def build_mermaid(data):
    """Mermaid: сверху вниз (источники → финал), flowchart TD."""
    lines = ["```mermaid", "flowchart TD"]
    steps = data.get("lineage_steps") or []
    if not steps:
        lines.append("  empty[Нет шагов lineage]")
    final_obj = (data.get("final_object") or "").strip()
    indexed = list(enumerate(steps))
    indexed.sort(
        key=lambda it: (
            1 if (it[1].get("writes_to") or "") == final_obj else 0,
            it[0],
        )
    )
    for i, step in indexed:
        proc = _node_id("p{0}".format(i))
        wt = _node_id("t{0}".format(i))
        lines.append('  {0}["{1}"]'.format(proc, _label(_short(step.get("procedure")))))
        lines.append('  {0}["{1}"]'.format(wt, _label(_short(step.get("writes_to")))))
        lines.append("  {0} --> {1}".format(proc, wt))
        for j, src in enumerate((step.get("reads_from") or [])[:5]):
            sid = _node_id("s{0}_{1}".format(i, j))
            lines.append('  {0}["{1}"] --> {2}'.format(sid, _label(_short(src)), proc))
    lines.append("```")
    return "\n".join(lines)


def format_schedule_section(data):
    return format_run_order_section(data)


def build_technical_md(data):
    title = data.get("report_title") or ""
    final_obj = data.get("final_object") or ""
    steps = data.get("lineage_steps") or []
    sources = lineage_store.inventory_sources(data)
    intermediate = (data.get("inventory") or {}).get("intermediate") or []
    transforms = (data.get("inventory") or {}).get("related_transforms") or []

    parts = [
        "# Техническое описание — {0}".format(title),
        "",
        "**Финал:** `{0}`".format(final_obj),
        "",
        "## 1. Назначение",
        "",
        "Отчёт `{0}`. Целевая витрина `{1}`.".format(title, final_obj),
        "",
        "## 2. Схема lineage",
        "",
        "Визуал сверху вниз (источники сверху → финал снизу). "
        "Под каждым шагом: день(ru) + типичное время запуска (полностью).",
        "",
        "![Lineage](lineage.svg)",
        "",
        "<details><summary>Mermaid (текстовый дубль, flowchart TD)</summary>",
        "",
        build_mermaid(data),
        "",
        "</details>",
        "",
        "## 3. Шаги сборки",
        "",
        "_Процедура: имя | пишет в | читает. View: имя view | пишет в (= view) | читает. "
        "View в «читает» родителя оставлять как есть — отдельный шаг по view._",
        "",
        "| # | Процедура / view | Пишет в | Читает | Роль |",
        "|---|------------------|---------|--------|------|",
    ]
    for i, step in enumerate(steps, 1):
        reads = ", ".join("`{0}`".format(_short(r)) for r in (step.get("reads_from") or [])[:8])
        parts.append(
            "| {0} | `{1}` | `{2}` | {3} | {4} |".format(
                i,
                _short(step.get("procedure") or ""),
                _short(step.get("writes_to") or ""),
                reads or "—",
                step.get("write_role") or step.get("branch_role") or "—",
            )
        )
    if not steps:
        parts.append("| — | — | — | — | — |")

    parts.extend(["", "## 4. Источники", ""])
    if sources:
        for t in sources:
            parts.append("- `{0}`".format(t))
    else:
        parts.append("_Пока пусто — update_inventory(sources=…)._")

    if intermediate:
        parts.extend(["", "### Промежуточные витрины", ""])
        for t in intermediate:
            parts.append("- `{0}`".format(t))

    if transforms:
        parts.extend(["", "### Смежные функции преобразований", ""])
        for t in transforms:
            parts.append("- `{0}`".format(t))

    parts.append("")
    parts.append(format_schedule_section(data))

    parts.extend(["## 6. Риски и предложения по доработкам", ""])
    open_revs = [r for r in (data.get("revisions") or []) if r.get("status") == "open"]
    if open_revs:
        for r in open_revs:
            parts.append("- [{0}] {1}".format(r.get("id"), r.get("text")))
    else:
        parts.append("_Нет открытых revision._")
    parts.append("")
    return "\n".join(parts)


def build_business_md(data):
    title = data.get("report_title") or ""
    final_obj = data.get("final_object") or ""
    glossary = data.get("glossary_table") or ""
    sources = lineage_store.inventory_sources(data)
    intermediate = (data.get("inventory") or {}).get("intermediate") or []

    parts = [
        "# Бизнес-описание — {0}".format(title),
        "",
        "## 1. Для кого и зачем",
        "",
        "Витрина `{0}`.".format(final_obj),
        "",
        "Термины из справочника `{0}` (если доступен) — использовать в формулировках.".format(
            glossary
        ),
        "",
        "## 2. Финальный объект",
        "",
        "### `{0}`".format(final_obj),
        "",
        "**Смысл:** _заполнить._",
        "",
        "| Поле | Тип | Пример | Комментарий |",
        "|------|-----|--------|-------------|",
        "| _…_ | | | |",
        "",
        "## 3. Источники (смысл + поля)",
        "",
        "_Обязательно таблица полей по get_columns / семплам для каждого источника. "
        "Не путать с промежуточными витринами._",
        "",
    ]
    if sources:
        for obj in sources:
            parts.append("### `{0}`".format(obj))
            parts.append("")
            parts.append("**Смысл:** _заполнить._")
            parts.append("")
            parts.append("| Поле | Тип | Пример | Комментарий |")
            parts.append("|------|-----|--------|-------------|")
            parts.append("| _…_ | | | |")
            parts.append("")
    else:
        parts.append("_update_inventory(sources=…) после шага 6 протокола._")
        parts.append("")

    parts.extend([
        "## 4. Промежуточные витрины",
        "",
        "_Не источники. Кратко: роль в цепочке. Поля — по необходимости._",
        "",
    ])
    if intermediate:
        for obj in intermediate:
            parts.append("### `{0}`".format(obj))
            parts.append("")
            parts.append("**Роль в цепочке:** _заполнить._")
            parts.append("")
    else:
        parts.append("_Нет или ещё не размечены (inventory.intermediate)._")
        parts.append("")

    parts.append("## 5. Термины (glossary)")
    parts.append("")
    parts.append(
        "Читать `{0}`. Новые термины вносить только с согласия пользователя.".format(
            glossary
        )
    )
    parts.append("")
    parts.append("## Правки аналитика")
    parts.append("")
    parts.append("_Свободное поле._")
    parts.append("")
    return "\n".join(parts)


def build_run_order_sql(data):
    title = data.get("report_title") or ""
    lines = [
        "-- Run order: {0}".format(title),
        "-- Финал: {0}".format(data.get("final_object") or ""),
        "",
    ]
    for i, step in enumerate(data.get("lineage_steps") or [], 1):
        lines.append(
            "-- {0}. {1}  →  {2}".format(
                i, step.get("procedure"), step.get("writes_to")
            )
        )
        lines.append(
            "-- SELECT {0}();".format(step.get("procedure"))
        )
        lines.append("")
    if len(lines) <= 3:
        lines.append("-- Пока нет шагов lineage.")
    return "\n".join(lines)


def render_all(project_root, overwrite_business=False):
    data = manifest.require_manifest(project_root)
    root = Path(project_root)
    (root / "docs").mkdir(parents=True, exist_ok=True)

    svg = diagram_svg.build_lineage_svg(data)
    write_text_safe(root / "docs" / "lineage.svg", svg)

    write_text_safe(root / "docs" / "TECHNICAL.md", build_technical_md(data))

    biz_path = root / "docs" / "BUSINESS.md"
    if overwrite_business or not biz_path.is_file() or biz_path.stat().st_size < 80:
        write_text_safe(biz_path, build_business_md(data))
        business_written = True
    else:
        business_written = False

    write_text_safe(root / "sql" / "dml" / "00_run_order.sql", build_run_order_sql(data))

    docs = data.setdefault("doc_files", [])
    for rel in ("docs/TECHNICAL.md", "docs/BUSINESS.md", "docs/lineage.svg", "README.md"):
        if rel not in docs:
            docs.append(rel)
    dml = data.setdefault("dml_files", [])
    if "sql/dml/00_run_order.sql" not in dml:
        dml.append("sql/dml/00_run_order.sql")

    manifest.touch_status(data, phase="docs", summary="render_report_docs выполнен")
    manifest.save_manifest(project_root, data)
    return {
        "ok": True,
        "written": ["docs/TECHNICAL.md", "docs/lineage.svg", "sql/dml/00_run_order.sql"]
        + (["docs/BUSINESS.md"] if business_written else []),
        "business_preserved": not business_written,
        "steps_count": len(data.get("lineage_steps") or []),
        "diagram": "docs/lineage.svg",
    }


def _node_id(name):
    raw = (name or "x").replace(".", "_").replace("-", "_")
    out = []
    for ch in raw:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    s = "".join(out)
    if s and s[0].isdigit():
        s = "n_" + s
    return s or "n"


def _label(name):
    return (name or "").replace('"', "'")


def _short(name, max_len=48):
    s = (name or "").strip()
    if len(s) <= max_len:
        return s
    if "." in s:
        short = s.split(".")[-1]
        if len(short) <= max_len:
            return short
    return s[: max_len - 1] + "…"
