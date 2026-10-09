from __future__ import annotations
from typing import Any, Dict

class SummaryAgent:
    def __init__(self, llm_manager, prompt_loader, logger, trace_manager):
        self.llm = llm_manager
        self.prompts = prompt_loader
        self.logger = logger
        self.trace = trace_manager

    def summarize_widget(self, ctx, widget_meta: Dict[str, Any], evidence: Dict[str, Any]) -> Dict[str, Any]:
        template_id = widget_meta.get("prompt_template_id")
        system_prompt = self.prompts.get_system("widget_summary_system", template_id=template_id)
        user_payload = {
            "widget": {
                "id_widget": widget_meta.get("id_widget"),
                "title": widget_meta.get("widget_title"),
                "group_widget": widget_meta.get("group_widget"),
                "description_short": widget_meta.get("widget_description_short"),
            },
            "axis": evidence.get("axis", {}),
            "policy": evidence.get("policy", {}),
            "instructions": self.prompts.get_user_template("widget_summary_user_template", template_id=template_id),
            "evidence": evidence,
            "output_schema": self.prompts.get_schema("widget_summary_output_schema", template_id=template_id),
        }
        self.trace.event(ctx, "запрос_к_llm", { 
            "provider": getattr(self.llm, "provider", None),
            "id_виджета": widget_meta.get("id_widget"),
            "payload_keys": list(user_payload.keys()),
            "widget": user_payload.get("widget"),
            "policy": user_payload.get("policy"),
            "evidence": user_payload.get("evidence"),
        })
        result = self.llm.generate_json(system_prompt=system_prompt, user_payload=user_payload)

        self.trace.event(ctx, "ответ_llm", {
            "id_виджета": widget_meta.get("id_widget"),
            "id системного промпта": template_id,
            "результат": result,
        })
        return result
