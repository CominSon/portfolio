from __future__ import annotations
from typing import Dict
from .llm_manager import LLMManager

class FakeLLMManager(LLMManager):
    def generate_json(self, system_prompt: str, user_payload: Dict) -> Dict:
        evidence = user_payload.get("evidence", {})
        versions = (evidence.get("версии") or {}).get("все", [])
        return {
            "write_mode": "brief",
            "narrative_type": "stable",
            "headline": "Заглушка вывода (LLM_PROVIDER=fake)",
            "details": [f"Строк: {evidence.get('количество_строк')}", f"Версии: {versions}"],
            "drivers_to_mention": [],
            "alerts": [],
            "confidence": 0.1,
            "next_checks": ["Включить LLM_PROVIDER=gigachat и проверить JPY_API_TOKEN"]
        }
