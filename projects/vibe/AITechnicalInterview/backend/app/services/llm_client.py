"""HTTP-клиент к LLM с OpenAI-совместимым API (DeepSeek, GigaChat, и др.)."""
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class LlmClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def api_key(self) -> str:
        return self.settings.llm_api_key or self.settings.deepseek_api_key

    @property
    def base_url(self) -> str:
        return (self.settings.llm_base_url or self.settings.deepseek_base_url).rstrip("/")

    @property
    def model(self) -> str:
        return self.settings.llm_model or self.settings.deepseek_model

    @property
    def fallback_models(self) -> list[str]:
        primary = self.model
        legacy = self.settings.deepseek_model
        models = [primary]
        if legacy and legacy not in models:
            models.append(legacy)
        if "deepseek-chat" not in models and self.settings.llm_provider in ("", "deepseek"):
            models.append("deepseek-chat")
        return models

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.7,
    ) -> str:
        if self.settings.mock_ai or not self.api_key:
            return ""

        last_err: Exception | None = None
        for model in self.fallback_models:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        f"{self.base_url}/v1/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": model,
                            "messages": messages,
                            "temperature": temperature,
                        },
                    )
                    resp.raise_for_status()
                    data: dict[str, Any] = resp.json()
                    return data["choices"][0]["message"]["content"]
            except Exception as exc:
                last_err = exc
                logger.warning("LLM model %s failed: %s", model, exc)
        raise RuntimeError(f"LLM unavailable: {last_err}") from last_err
