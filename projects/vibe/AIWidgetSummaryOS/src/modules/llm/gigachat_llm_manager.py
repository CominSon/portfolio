from __future__ import annotations
import json
import os
import threading
from typing import Any, Dict
from decimal import Decimal
import datetime
import requests
from .llm_manager import LLMManager
from modules.gigachat.token_provider import GigaChatTokenProvider
from modules.gigachat.gigachat_client import GigaChatClient
import time
import random


class GigaChatLLMManager(LLMManager):
    """
    GigaChat с анти-троттлингом.
    У провайдера лимит: не более 5 параллельных запросов на ключ userId:modelId.
    """

    _spacing_lock = threading.Lock()
    _last_call_end_ts = 0.0
    _concurrency_sem: threading.Semaphore | None = None

    def __init__(self, provider: str, logger):
        super().__init__(provider=provider, logger=logger)
        self.token_provider = GigaChatTokenProvider(logger)
        self.client = GigaChatClient(self.token_provider, logger)

        # Анти-троттлинг / ретраи (настраиваются через env)
        self.min_interval_sec = float(os.getenv("LLM_MIN_INTERVAL_SEC", "1.5"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "8"))
        self.retry_base_sleep = float(os.getenv("LLM_RETRY_BASE_SLEEP_SEC", "2.0"))
        self.retry_429_base_sleep = float(os.getenv("LLM_RETRY_429_BASE_SLEEP_SEC", "8.0"))
        self.max_concurrent = int(os.getenv("LLM_MAX_CONCURRENT", "4"))

        if GigaChatLLMManager._concurrency_sem is None:
            GigaChatLLMManager._concurrency_sem = threading.Semaphore(self.max_concurrent)

    @classmethod
    def _get_concurrency_sem(cls) -> threading.Semaphore:
        if cls._concurrency_sem is None:
            limit = int(os.getenv("LLM_MAX_CONCURRENT", "4"))
            cls._concurrency_sem = threading.Semaphore(limit)
        return cls._concurrency_sem

    def _wait_min_interval(self) -> None:
        with self._spacing_lock:
            wait = self.min_interval_sec - (time.time() - GigaChatLLMManager._last_call_end_ts)
            if wait > 0:
                self.logger.info(f"Пауза перед вызовом LLM: {wait:.2f} сек (анти-троттлинг)")
                time.sleep(wait)

    def _mark_call_finished(self) -> None:
        with self._spacing_lock:
            GigaChatLLMManager._last_call_end_ts = time.time()

    def _json_defaults(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (datetime.date, datetime.datetime)):
            return o.isoformat()
        return str(0)

    def _extract_text(self, resp_json: Dict[str, Any]) -> str:
        try:
            return resp_json["choices"][0]["message"]["content"]
        except Exception:
            return json.dumps(resp_json, ensure_ascii=False, default=self._json_defaults)

    def generate_json(self, system_prompt: str, user_payload: Dict[str, Any]) -> Dict[str, Any]:
        model = os.getenv("GIGACHAT_MODEL")
        temperature = float(os.getenv("GIGACHAT_TEMPERATURE"))
        max_tokens = int(os.getenv("GIGACHAT_MAX_TOKENS"))

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=self._json_defaults)},
        ]

        self.logger.info(f"Вызов GigaChat: модель={model}, temperature={temperature}, max_tokens={max_tokens}")

        resp: Dict[str, Any] | None = None
        last_err: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            sem = self._get_concurrency_sem()
            sem.acquire()
            try:
                self._wait_min_interval()
                resp = self.client.chat_completions(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                self._mark_call_finished()
                last_err = None
                break
            except Exception as e:
                self._mark_call_finished()
                if (not self._is_retryable_llm_error(e)) or (attempt == self.max_retries):
                    raise

                sleep_s = self._retry_sleep_seconds(e, attempt)
                self.logger.warning(
                    f"Временная ошибка LLM ({type(e).__name__}: {e}). "
                    f"Попытка {attempt}/{self.max_retries}. Ждём {sleep_s:.1f} сек и повторяем вызов."
                )
                last_err = e
            finally:
                sem.release()

            if last_err is not None:
                time.sleep(sleep_s)

        if last_err is not None:
            raise last_err
        if resp is None:
            raise RuntimeError("GigaChat: пустой ответ после ретраев")

        text = self._extract_text(resp).strip()

        if text.startswith("```"):
            text = text.strip("`")
            text = text.replace("json", "", 1).strip()

        try:
            return json.loads(text)
        except Exception as e:
            return {
                "write_mode": "brief",
                "narrative_type": "stable",
                "headline": "Не удалось распарсить JSON от модели",
                "details": [f"Ошибка: {type(e).__name__}: {e}"],
                "drivers_to_mention": [],
                "alerts": ["Ответ модели не валидный JSON"],
                "confidence": 0.0,
                "next_checks": ["Если ошибка endpoint — задайте GIGACHAT_CHAT_URL"],
            }

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return "http 429" in msg or "throttle" in msg or '"statuscode":429' in msg

    def _retry_sleep_seconds(self, exc: Exception, attempt: int) -> float:
        if self._is_rate_limit_error(exc):
            # Лимит 5 параллельных запросов на userId:modelId — ждём дольше, чтобы слот освободился.
            sleep_s = min(self.retry_429_base_sleep * (2 ** (attempt - 1)), 60.0)
            return sleep_s + random.uniform(0.5, 2.0)
        return self.retry_base_sleep * attempt + random.uniform(0.0, 1.5)

    def _is_retryable_llm_error(self, exc: Exception) -> bool:
        """Временные ошибки GigaChat/сети, при которых имеет смысл повторить запрос."""
        if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
            return True

        msg = str(exc).lower()
        retry_markers = (
            "http 429",
            "http 503",
            "http 502",
            "http 504",
            "http 408",
            "throttle",
            '"statuscode":429',
            "upstream connect error",
            "connection termination",
            "disconnect/reset",
            "temporarily unavailable",
            "ошибка сети при вызове gigachat",
        )
        return any(marker in msg for marker in retry_markers)
