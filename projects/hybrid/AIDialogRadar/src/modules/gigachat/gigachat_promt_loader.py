import json


class GigaChatPromptLoader:
    """Класс обработки промтов"""

    def __init__(self, logger, path: str = "resources/prompts.json"):
        self.logger = logger
        self.path = path
        self.prompts = self.load_prompts()

    def build_system_context(self):
        context = self.prompts.get("context", {})
        abbr = context.get("abbreviations", {})
        common = context.get("common_knowledge", "")
        abbr_text = "\n".join(f"{k} - {v}" for k, v in abbr.items())
        return f"{common}\n\nСписок терминов:\n{abbr_text}"

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
