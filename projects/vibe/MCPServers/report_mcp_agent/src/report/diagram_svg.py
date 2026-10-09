"""SVG lineage: сверху вниз (источники сверху → финал снизу), день+время без обрезки."""

from html import escape

from report_mcp_agent.src.report.schedule_format import (
    collect_schedule_entries,
    entry_schedule_label,
)


def build_lineage_svg(data, width=1280):
    steps = data.get("lineage_steps") or []
    if not steps:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="480" height="80">'
            '<text x="16" y="40" font-family="Segoe UI,Arial,sans-serif" font-size="14">'
            "Нет шагов lineage</text></svg>"
        )

    schedule_map = _schedule_lookup(data)
    final_obj = (data.get("final_object") or "").strip()

    # Сверху источники/ранние шаги, снизу финал
    indexed = list(enumerate(steps))
    indexed.sort(
        key=lambda it: (
            1 if (it[1].get("writes_to") or "") == final_obj else 0,
            it[0],
        )
    )
    ordered_steps = [s for _, s in indexed]

    rows = []
    for step in ordered_steps:
        proc = step.get("procedure") or "?"
        wt = step.get("writes_to") or "?"
        reads = list(step.get("reads_from") or [])[:5]
        edge_label = _edge_label(schedule_map, proc, wt)
        if not edge_label or edge_label == "расп. ?":
            edge_label = "время?"
        rows.append({
            "proc_lines": _name_lines(proc),
            "writes_lines": _name_lines(wt),
            "reads_lines": _reads_lines(reads),
            "edge": edge_label,
        })

    margin = 28
    gap = 90  # место под подпись расписания между колонками (не обрезать)
    col_src = 16
    box_w = (width - 2 * margin - 2 * gap) // 3
    col_proc = col_src + box_w + gap
    col_tgt = col_proc + box_w + gap
    line_h = 11
    pad_y = 8
    sched_band = 22  # полоса под строкой для полного времени

    row_heights = []
    for row in rows:
        nlines = max(
            len(row["reads_lines"]),
            len(row["proc_lines"]),
            len(row["writes_lines"]),
            1,
        )
        row_heights.append(max(40, pad_y * 2 + nlines * line_h + 6) + sched_band)

    height = margin * 2 + sum(row_heights) + 36
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="{0}" height="{1}">'.format(
            width, height
        ),
        "<defs>",
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">',
        '<path d="M0,0 L6,3 L0,6 Z" fill="#334155"/>',
        "</marker>",
        "</defs>",
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        '<text x="{0}" y="16" font-family="Segoe UI,Arial,sans-serif" font-size="11" fill="#475569">'
        "Сверху вниз: источники → процедура/view → пишет в (финал снизу). "
        "Под строкой: день(ru) + типичное время полностью"
        "</text>".format(margin),
    ]

    y = margin + 22
    for i, row in enumerate(rows):
        box_h = row_heights[i] - sched_band
        mid_y = y + box_h // 2
        parts.append(_box_multiline(col_src, y, box_w, box_h, row["reads_lines"], "#e2e8f0"))
        x1 = col_src + box_w
        x2 = col_proc
        parts.append(_line(x1, mid_y, x2, mid_y))
        parts.append(_box_multiline(col_proc, y, box_w, box_h, row["proc_lines"], "#dbeafe"))
        x3 = col_proc + box_w
        x4 = col_tgt
        parts.append(_line(x3, mid_y, x4, mid_y))
        parts.append(_box_multiline(col_tgt, y, box_w, box_h, row["writes_lines"], "#dcfce7"))
        # Расписание — отдельная полоса на всю ширину строки (не в узком зазоре стрелки)
        sched_y = y + box_h + 14
        parts.append(_schedule_band(col_src, sched_y, col_tgt + box_w - col_src, row["edge"]))
        y += row_heights[i] + 10

    parts.append(
        '<text x="{0}" y="{1}" font-family="Segoe UI,Arial,sans-serif" font-size="10" fill="#64748b">'
        "↓ к финальному объекту"
        "</text>".format(margin, height - 8)
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _schedule_band(x, y, width, text):
    """Полная подпись расписания по центру полосы — без обрезки."""
    label = (text or "").strip() or "время?"
    return (
        '<text x="{0}" y="{1}" text-anchor="middle" '
        'font-family="Segoe UI,Arial,sans-serif" font-size="11" font-weight="600" '
        'fill="#b45309">{2}</text>'
    ).format(x + width // 2, y, escape(label))


def _schedule_lookup(data):
    out = {}
    for e in collect_schedule_entries(data):
        label = entry_schedule_label(e)
        if not label:
            continue
        for key in (e.get("object"), e.get("target"), e.get("pxf_table_name")):
            if key:
                out[key] = label
                if "." in str(key):
                    out[str(key).split(".")[-1]] = label
    for step in data.get("lineage_steps") or []:
        sched = step.get("schedule") or {}
        if isinstance(sched, dict):
            label = entry_schedule_label({"summary": sched, **sched})
            if label and step.get("procedure"):
                out[step["procedure"]] = label
    return out


def _edge_label(schedule_map, proc, writes_to):
    for key in (proc, writes_to):
        if key in schedule_map:
            return schedule_map[key]
        if key and "." in key and key.split(".")[-1] in schedule_map:
            return schedule_map[key.split(".")[-1]]
    return "расп. ?"


def _name_lines(name, max_chars=28):
    s = (name or "").strip() or "?"
    if "." in s:
        sch, obj = s.split(".", 1)
        lines = _wrap_token(sch, max_chars) + _wrap_token(obj, max_chars)
    else:
        lines = _wrap_token(s, max_chars)
    return lines[:4] or ["?"]


def _reads_lines(reads, max_chars=28):
    if not reads:
        return ["—"]
    lines = []
    for r in reads:
        lines.extend(_name_lines(r, max_chars=max_chars))
    return lines[:6]


def _wrap_token(token, max_chars):
    token = token or ""
    if len(token) <= max_chars:
        return [token]
    parts = token.split("_")
    if len(parts) == 1:
        return [token[i : i + max_chars] for i in range(0, len(token), max_chars)]
    lines = []
    cur = parts[0]
    for p in parts[1:]:
        trial = cur + "_" + p
        if len(trial) <= max_chars:
            cur = trial
        else:
            lines.append(cur)
            cur = p
    if cur:
        lines.append(cur)
    final = []
    for line in lines:
        if len(line) <= max_chars:
            final.append(line)
        else:
            for i in range(0, len(line), max_chars):
                final.append(line[i : i + max_chars])
    return final or [token[:max_chars]]


def _box_multiline(x, y, w, h, lines, fill):
    font_size = 9 if max(len(t) for t in lines) > 22 or len(lines) > 2 else 10
    text_x = x + 6
    start_y = y + 12
    tspans = []
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else font_size + 1
        tspans.append(
            '<tspan x="{0}" dy="{1}">{2}</tspan>'.format(
                text_x, dy, escape(line)
            )
        )
    return (
        '<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{fill}" '
        'stroke="#94a3b8"/>'
        '<text x="{tx}" y="{ty}" font-family="Segoe UI,Consolas,monospace" '
        'font-size="{fs}" fill="#0f172a">{tspans}</text>'
    ).format(
        x=x,
        y=y,
        w=w,
        h=h,
        fill=fill,
        tx=text_x,
        ty=start_y,
        fs=font_size,
        tspans="".join(tspans),
    )


def _line(x1, y1, x2, y2):
    return (
        '<line x1="{0}" y1="{1}" x2="{2}" y2="{3}" stroke="#334155" '
        'stroke-width="1.5" marker-end="url(#arrow)"/>'
    ).format(x1, y1, x2, y2)
