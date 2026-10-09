from __future__ import annotations
from typing import Any, Dict, List
import os
from datetime import datetime
from pathlib import Path
 
class ReportRenderer:
    def __init__(self, result_dir: str | None, logger):
        self.result_dir = (result_dir or "src/result").strip() or "src/result"
        self.logger = logger
        Path(self.result_dir).mkdir(parents=True, exist_ok=True)
 
    def render_group_txt(self, group_widget: str, widget_results: List[Dict[str, Any]], final_report=None) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fp = os.path.join(self.result_dir, f"отчёт_{group_widget}_{ts}.txt")
 
        lines = []
        #lines.append(f"Группа: {group_widget}")
        lines.append(f"**Сформировано: {datetime.now().isoformat(timespec='seconds')}**")
        lines.append("=" * 80)
 
        # ===== Финальный вывод по группе ===== 
        if final_report and isinstance(final_report, dict):
            sections = final_report.get("sections", [])
            if sections:
                for section in sections:
                    title = section.get("title")
                    lines_list = section.get("lines") or section.get("items") or []
                    subsections = section.get("subsections") or []
                    non_empty_subsections = [
                        subsection for subsection in subsections
                        if subsection.get("title") and (subsection.get("lines") or subsection.get("items"))
                    ]
 
                    if not lines_list and not non_empty_subsections:
                        continue
 
                    lines.append("")
                    lines.append(str(title or ""))
                    lines.append("-" * 80)

                    for line in lines_list:
                        lines.append(f"- {line}")

                    for subsection in non_empty_subsections:
                        subsection_title = subsection.get("title")
                        subsection_lines = subsection.get("lines") or subsection.get("items") or []
                        lines.append("")
                        lines.append(str(subsection_title or ""))

                        for line in subsection_lines:
                            lines.append(f"- {line}")

        if widget_results is None:
            widget_results = []
        if not widget_results and not (final_report and final_report.get("sections")):
            lines.append("Нет виджетов в метаданных для этой группы.")
            lines.append("Заполните таблицу ai_os_ub_widget_meta и повторите запуск.")

        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
 
        self.logger.info(f"Отчёт сохранён: {fp}")
        return fp
