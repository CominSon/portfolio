from __future__ import annotations
import os
import requests
from typing import Any, Dict, List

class GigaChatClient:
    """Минимальный REST-клиент GigaChat: URL + токен + модель."""

    def __init__(self, token_provider, logger):
        self.token_provider = token_provider
        self.logger = logger
        self.base_url = os.getenv("GIGACHAT_BASE_URL", "").rstrip("/")
        self.chat_url = os.getenv("GIGACHAT_CHAT_URL")  # опционально

    def chat_completions(self, messages: List[Dict[str, str]], model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
        #token = self.token_provider.get_token()
        url = self.chat_url or (self.base_url + "/chat/completions")
        if not url.startswith("http"):
            raise RuntimeError("Не задан корректный GIGACHAT_BASE_URL (или GIGACHAT_CHAT_URL)")

        #headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=200)
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Ошибка сети при вызове GigaChat: {type(e).__name__}: {e}") from e

        if resp.status_code >= 400:
            raise RuntimeError(f"Ошибка вызова GigaChat: HTTP {resp.status_code} | {resp.text[:800]}")
        return resp.json()
