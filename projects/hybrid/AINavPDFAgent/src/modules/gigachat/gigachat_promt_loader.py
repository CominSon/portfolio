import json


class GigaChatPromptLoader:
    """Класс обработки промтов"""

    def __init__(self, logger, path: str = "resources/prompts.json"):
        self.logger = logger
        self.path = path
        self.prompts = self.load_prompts()

    def build_system_text(self, prompt):
        """
        Возвращает единый многострочный system-prompt.
        """
        sys_prompt = self.get_prompt(key=prompt)
        if isinstance(sys_prompt, str):
            return sys_prompt.strip()

        intro = sys_prompt.get("intro", "").strip()
        rules = sys_prompt.get("rules", []) or []
        #responses = sys_prompt.get("responses", {}) or {}
        parts = []
        if intro:
            parts.append(intro)

        if rules:
            parts.append("Правила:")
            parts.extend([f"- {r}" for r in rules])
        """
        if responses:
            parts.append("Шаблоны ответов (используй при необходимости):")
            for k, v in responses.items():
                parts.append(f"- {k}: {v}")
        """
        return "\n".join(parts).strip()

    def load_prompts(self) -> dict:
        """Загружаем json с промтами"""
        try:
            with open(self.path, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            self.logger.error(f"Ошибка чтения JSON: {e}")
            raise ValueError(f"Ошибка чтения JSON: {e}")

    def get_prompt(self, key: str) -> str:
        prompt = self.prompts.get(key)
        if not prompt:
            self.logger.error(f"Промт с ключом '{key}' не найден в {self.path}")
            raise KeyError(f"Промт с ключом '{key}' не найден в {self.path}")
        return prompt
