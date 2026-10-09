from __future__ import annotations
 
import re
from typing import Any, Dict, List

from modules.core.navigator_formatter import NavigatorFormatter

class FinalQualityAgent:
    """
    Проверяет и аккуратно правит уже собранный финальный отчёт.
    Все LLM-инструкции берутся только из БД (template_id=3).
    """
 
    TEMPLATE_ID = 3
    MONTHS_PATTERN = re.compile(
        r"\b("
        r"январь|января|февраль|февраля|март|марта|апрель|апреля|май|мая|"
        r"июнь|июня|июль|июля|август|августа|сентябрь|сентября|"
        r"октябрь|октября|ноябрь|ноября|декабрь|декабря"
        r")\b",
        flags=re.IGNORECASE,
    )
 
    def __init__(self, llm_manager, prompt_loader, logger, trace_manager):
        self.llm = llm_manager
        self.prompts = prompt_loader
        self.logger = logger
        self.trace = trace_manager
        self.navigator_formatter = NavigatorFormatter()
 
    def review(self, ctx, group_widget: str, final_report: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(final_report, dict):
            return final_report
 
        system_prompt = self.prompts.get_system("final_quality_system", template_id=self.TEMPLATE_ID)
        rules = self.prompts.get_user_template("final_quality_user_template", template_id=self.TEMPLATE_ID)
        schema = self.prompts.get_schema("final_quality_output_schema", template_id=self.TEMPLATE_ID)
        user_payload = {
            "group_widget": group_widget,
            "final_report": final_report,
            "check_rules": rules,
            "output_schema": schema,
        }
 
        self.trace.event(ctx, "запрос_к_llm_final_quality", {
            "provider": getattr(self.llm, "provider", None),
            "group_widget": group_widget,
            "system_prompt": str(system_prompt),
            "user_payload": str(user_payload),
        })
 
        reviewed = self.llm.generate_json(system_prompt=system_prompt, user_payload=user_payload)
        self.trace.event(ctx, "сырой_ответ_llm_final_quality", {
            "group_widget": group_widget,
            "result": reviewed,
        })
        if not self._looks_like_report(reviewed):
            self.logger.warning("Агент проверки вернул невалидную структуру, оставляю исходный финальный отчёт")
            reviewed = final_report
 
        #reviewed = self._cleanup_duplicate_metric_lines(reviewed)
        reviewed = self._cleanup_empty_subsections(reviewed)
        reviewed = self._format_numbers(reviewed)
        reviewed = self.navigator_formatter.format_report(reviewed)

        self.trace.event(ctx, "ответ_llm_final_quality", {
            "group_widget": group_widget,
            "result": reviewed,
        })
        return reviewed
 
    def _looks_like_report(self, value: Any) -> bool:
        return isinstance(value, dict) and isinstance(value.get("sections"), list)
 
    def _cleanup_duplicate_metric_lines(self, report: Dict[str, Any]) -> Dict[str, Any]:
        sections = report.get("sections")
        if not isinstance(sections, list):
            return report
 
        seen_titles = set()
        for section in sections:
            if not isinstance(section, dict):
                continue
            cleaned_lines = []
            for line in section.get("lines") or []:
                metric_title = self._metric_title(line)
                if metric_title and metric_title in seen_titles:
                    continue
                if metric_title:
                    seen_titles.add(metric_title)
                cleaned_lines.append(line)
            section["lines"] = cleaned_lines
 
            subsections = section.get("subsections")
            if not isinstance(subsections, list):
                continue
            for subsection in subsections:
                if not isinstance(subsection, dict):
                    continue
                cleaned_subsection_lines = []
                for line in subsection.get("lines") or []:
                    metric_title = self._metric_title(line)
                    if metric_title and metric_title in seen_titles:
                        continue
                    if metric_title:
                        seen_titles.add(metric_title)
                    cleaned_subsection_lines.append(line)
                subsection["lines"] = cleaned_subsection_lines
 
        return report
 
    def _cleanup_empty_subsections(self, report: Dict[str, Any]) -> Dict[str, Any]:
        sections = report.get("sections")
        if not isinstance(sections, list):
            return report
 
        for section in sections:
            if not isinstance(section, dict):
                continue
            subsections = section.get("subsections")
            if not isinstance(subsections, list):
                continue
            section["subsections"] = [
                subsection
                for subsection in subsections
                if isinstance(subsection, dict)
                and subsection.get("title")
                and (subsection.get("lines") or subsection.get("items"))
            ]
 
        return report
 
    def _format_numbers(self, report: Dict[str, Any]) -> Dict[str, Any]:
        sections = report.get("sections")
        if not isinstance(sections, list):
            return report
 
        for section in sections:
            if not isinstance(section, dict):
                continue
            section["lines"] = [self._format_text_numbers(line) for line in (section.get("lines") or [])]
            subsections = section.get("subsections")
            if not isinstance(subsections, list):
                continue
            for subsection in subsections:
                if not isinstance(subsection, dict):
                    continue
                subsection["lines"] = [
                    self._format_text_numbers(line) for line in (subsection.get("lines") or [])
                ]
 
        return report
 
    def _format_text_numbers(self, value: Any) -> str:
        text = str(value or "")
 
        def percent_replacer(match: re.Match[str]) -> str:
            original_number = match.group(1)
            raw_number = original_number.replace(",", ".")
            try:
                number = float(raw_number)
            except ValueError:
                return match.group(0).replace(" %", "%")
            if "." not in original_number and "," not in original_number:
                return f"{int(round(number))}%"
            return f"{number:.1f}%"

        text = re.sub(r"(\d+(?:[.,]\d+)?)\s*%", percent_replacer, text)
        # Только десятичная запятая между цифрами -> точка; запятые в тексте не трогаем.
        text = re.sub(r"(?<=\d),(?=\d)", ".", text)
        return self.MONTHS_PATTERN.sub(lambda match: match.group(1).lower(), text)
 
    def _line_metric_titles(self, lines: List[Any]) -> set[str]:
        return {self._metric_title(line) for line in lines if self._metric_title(line)}
 
    def _metric_title(self, line: Any) -> str:
        text = str(line or "").strip().lower()
        if not text:
            return ""
        for sep in (":", "("):
            if sep in text:
                text = text.split(sep, 1)[0].strip()
                break
        return text
