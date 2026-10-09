from __future__ import annotations
import os

class GigaChatTokenProvider:
    """Токен берём из системной переменной окружения JPY_API_TOKEN."""

    def __init__(self, logger):
        self.logger = logger

    def get_token(self) -> str:
        tok = os.getenv("JPY_API_TOKEN")
        if not tok:
            raise RuntimeError("Не найден токен: переменная окружения JPY_API_TOKEN не задана")
        return tok.strip()
