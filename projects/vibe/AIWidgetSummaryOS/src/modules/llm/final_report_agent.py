from __future__ import annotations 
 
from typing import Any, Dict, List
 
class FinalReportAgent:
    """
    Делает финальный текст по группе на основе результатов по виджетам.
    Не меняет логику should_write — берёт то, что уже решили раньше.
    """
 
    def __init__(self, llm_manager, prompt_loader, logger, trace_manager):
        self.llm = llm_manager
        self.prompts = prompt_loader
        self.logger = logger
        self.trace = trace_manager
 
    def build_final_report(self, ctx, group_widget: str, widget_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Берём только то, что уже “разрешено” показывать
        items: List[Dict[str, Any]] = []
        
        for r in (widget_results or []):
            summary = (r or {}).get("summary") or {}
            evidence = (r or {}).get("evidence") or {}
 
            # Теги для раскладки по секциям (LLM будет ими пользоваться)
            policy = (evidence or {}).get("policy") or {}
            zones = (evidence or {}).get("zones") or {}
            decision = (evidence or {}).get("decision") or {}
            pct_last = (((evidence or {}).get("measures") or {}).get("pct") or {}).get("last")
            attention_section = self._attention_section(policy)
            items.append({
                "widget_id": r.get("widget_id"),
                "title": ((evidence.get("widget_title") or "").strip()),
                "headline_raw": (summary.get("headline") or "").strip(),
                "pct": pct_last,
                "is_key": False,
                "attention_section": attention_section,
                "attention_focus_eligible": self._attention_focus_eligible(policy, attention_section, pct_last),
                "zone_last": zones.get("zone_last"),
                "transition": zones.get("transition_code"),  # "red_to_green" / "green_to_red" / None
                "wow_delta_points": decision.get("wow_delta_points"),
                "insight_eligible": not bool(decision.get("only_attention")),
                "trigger_reasons": decision.get("reasons") or [],
            })
        system_prompt = self.prompts.get_system("group_summary_system", template_id=2)
        user_payload = {
            "group_widget": group_widget,
            "items": items,
            "output_schema": self.prompts.get_schema("group_summary_output_schema", template_id=2),
        }
 
        self.trace.event(ctx, "запрос_к_llm_group", {
            "provider": getattr(self.llm, "provider", None),
            "group_widget": group_widget,
            "items_cnt": len(items),
            "system_prompt": str(system_prompt),
            "user_payload": str(user_payload)
        })
        result = self.llm.generate_json(system_prompt=system_prompt, user_payload=user_payload)
        self.trace.event(ctx, "сырой_ответ_llm_group", {
            "group_widget": group_widget,
            "result": result,
        })
        result = self._cleanup_insights_for_attention_only_items(result, items)
        result = self._enforce_attention_section(result, items)
 
        self.trace.event(ctx, "ответ_llm_group", {
            "group_widget": group_widget,
            "result": result,
        })
 
        return result

    def _enforce_attention_section(self, result: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Зона внимания строится строго по тегам, без права LLM потерять red-показатель.
        """
        if not isinstance(result, dict):
            return result

        attention_subsections = [
            {"title": "Цели", "lines": []},
            {"title": "Фокусные метрики", "lines": []},
        ]
        subsection_by_key = {
            "goals": attention_subsections[0],
            "focus_metrics": attention_subsections[1],
        }

        for item in items or []:
            if item.get("zone_last") != "red":
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            section_key = item.get("attention_section") or "goals"
            if section_key == "focus_metrics" and not bool(item.get("attention_focus_eligible")):
                continue
            subsection = subsection_by_key.get(section_key, subsection_by_key["goals"])
            subsection["lines"].append(f"{title} ({self._format_pct(item.get('pct'))})")

        attention_subsections = [
            subsection for subsection in attention_subsections
            if subsection.get("lines")
        ]

        sections = result.get("sections")
        if not isinstance(sections, list):
            sections = []
            result["sections"] = sections

        attention_section = {
            "title": "Зона внимания",
            "lines": [],
            "subsections": attention_subsections,
        }

        for idx, section in enumerate(sections):
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or "").strip().lower()
            if "зона внимания" in title:
                if attention_subsections:
                    sections[idx] = attention_section
                else:
                    sections.pop(idx)
                return result

        if attention_subsections:
            sections.insert(0, attention_section)
        return result
 
    def _attention_section(self, policy: Dict[str, Any]) -> str:
        section = str((policy or {}).get("attention_section") or "").strip().lower()
        if section == "focus_metrics":
            return "focus_metrics"
        return "goals"
 
    def _attention_focus_eligible(self, policy: Dict[str, Any], attention_section: str, pct: Any) -> bool:
        if attention_section != "focus_metrics":
            return False
        threshold = self._to_float((policy or {}).get("attention_focus_pct_lt"))
        threshold = 95.0 if threshold is None else threshold
        pct_value = self._to_float(pct)
        return pct_value is not None and pct_value < threshold

 
    def _to_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(str(value).replace(",", ".").replace("%", "").strip())
        except (TypeError, ValueError):
            return None

    def _format_pct(self, value: Any) -> str:
        number = self._to_float(value)
        if number is None:
            return ""
        return f"{number:.1f}%"
 
    def _cleanup_insights_for_attention_only_items(self, result: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Страховка от дублей:
        если элемент помечен только для "Зоны внимания", удаляем его из "Инсайты на данных"
        даже если LLM-шаблон в БД ещё не обновлён.
        """
        if not isinstance(result, dict):
            return result
 
        blocked_titles = {
            (it.get("title") or "").strip().lower()
            for it in (items or [])
            if not bool(it.get("insight_eligible"))
        }
        if not blocked_titles:
            return result
 
        sections = result.get("sections")
        if not isinstance(sections, list):
            return result
 
        for section in sections:
            if not isinstance(section, dict):
                continue
            title = (section.get("title") or "").strip().lower()
            if "инсайт" not in title and "динамика" not in title and "тренд" not in title:
                continue
            lines = section.get("lines")
            if not isinstance(lines, list):
                continue
 
            cleaned_lines = []
            for line in lines:
                line_text = str(line or "").strip()
                line_lower = line_text.lower()
                is_blocked = any(
                    line_lower.startswith(f"{blocked}:")
                    or line_lower.startswith(f"{blocked} ")
                    or line_lower == blocked
                    for blocked in blocked_titles
                )
                if not is_blocked:
                    cleaned_lines.append(line)
            section["lines"] = cleaned_lines
 
        return result
