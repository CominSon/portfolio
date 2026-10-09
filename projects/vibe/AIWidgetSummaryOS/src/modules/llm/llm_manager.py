from __future__ import annotations
from typing import Dict

class LLMManager:
    def __init__(self, provider: str, logger):
        self.provider = provider
        self.logger = logger

    def generate_json(self, system_prompt: str, user_payload: Dict) -> Dict:
        raise NotImplementedError
