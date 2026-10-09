"""Голосовой конвейер: STT (faster-whisper), TTS (Silero, локально, без Microsoft)."""
import asyncio
import logging
import os
import tempfile
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.services.interview_dialog_policy import collapse_stt_repetition
from app.services.stt_providers import (
    SttProviderError,
    transcribe_openai_whisper,
    transcribe_yandex_speechkit,
    transcribe_yandex_speechkit_from_path,
)
from app.services.stt_sanitize import sanitize_stt_text
from app.services.tts_edge import synthesize_edge_mp3
from app.services.tts_prepare import prepare_for_tts
from app.services.tts_silero import synthesize_to_wav
from app.services.tts_yandex import synthesize_yandex_mp3

logger = logging.getLogger(__name__)


class SttUnavailableError(Exception):
    """faster-whisper не установлен или недоступен."""


class VoicePipeline:
    """Распознавание речи кандидата и синтез голоса AI."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._whisper_model = None
        self._whisper_lock = asyncio.Lock()
        self.tts_dir = Path(self.settings.recordings_dir) / "tts"
        self.tts_dir.mkdir(parents=True, exist_ok=True)

    def _cpu_threads(self) -> int:
        configured = self.settings.stt_cpu_threads
        if configured and configured > 0:
            return configured
        return os.cpu_count() or 4

    def _load_whisper(self):
        if self._whisper_model is not None:
            return self._whisper_model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise SttUnavailableError(
                "Модуль faster-whisper не установлен. "
                "Выполните: pip install faster-whisper"
            ) from exc

        t0 = time.perf_counter()
        self._whisper_model = WhisperModel(
            self.settings.stt_model,
            device=self.settings.stt_device,
            compute_type=self.settings.stt_compute_type,
            cpu_threads=self._cpu_threads(),
        )
        logger.info(
            "Whisper STT loaded: model=%s device=%s compute=%s (%.1fs)",
            self.settings.stt_model,
            self.settings.stt_device,
            self.settings.stt_compute_type,
            time.perf_counter() - t0,
        )
        return self._whisper_model

    async def warmup_stt(self) -> None:
        """Предзагрузка локальной модели при старте API (только whisper)."""
        provider = (self.settings.stt_provider or "whisper").lower()
        if provider in ("openai", "yandex"):
            logger.info("STT warmup skipped: cloud provider=%s", provider)
            return
        await asyncio.to_thread(self._load_whisper)

    async def speech_to_text_from_path(self, path: str, *, use_vad: bool | None = None) -> str:
        """STT для локального файла (полная аудиодорожка интервью)."""
        provider = (self.settings.stt_provider or "whisper").lower()
        t0 = time.perf_counter()
        try:
            if provider == "yandex":
                text = await transcribe_yandex_speechkit_from_path(path, self.settings)
            elif provider == "openai":
                data = Path(path).read_bytes()
                text = await transcribe_openai_whisper(data, Path(path).name, self.settings)
            else:
                async with self._whisper_lock:
                    text = await asyncio.to_thread(self._transcribe_file, path, use_vad=use_vad)
            text = sanitize_stt_text(collapse_stt_repetition(text))
            logger.info(
                "STT(file) %.2fs | %d chars | %s",
                time.perf_counter() - t0,
                len(text),
                path,
            )
            return text
        except SttProviderError:
            raise
        except SttUnavailableError:
            raise
        except Exception:
            logger.warning("STT(file) failed path=%s", path, exc_info=True)
            return ""

    def _transcribe_file(self, path: str, *, use_vad: bool | None = None) -> str:
        model = self._load_whisper()
        prompt = (self.settings.stt_initial_prompt or "").strip() or None
        vad = self.settings.stt_vad_filter if use_vad is None else use_vad
        segments, _ = model.transcribe(
            path,
            language=self.settings.stt_language or "ru",
            beam_size=max(1, self.settings.stt_beam_size),
            best_of=1,
            temperature=0.0,
            condition_on_previous_text=True,
            vad_filter=vad,
            vad_parameters={
                "min_silence_duration_ms": 1200,
                "speech_pad_ms": 400,
                "min_speech_duration_ms": 200,
            },
            initial_prompt=prompt,
            without_timestamps=True,
            compression_ratio_threshold=2.6,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.55,
        )
        raw = " ".join(s.text.strip() for s in segments).strip()
        return collapse_stt_repetition(raw)

    async def speech_to_text(self, audio_bytes: bytes, *, filename: str = "answer.webm") -> str:
        if len(audio_bytes) < 200:
            return ""

        provider = (self.settings.stt_provider or "whisper").lower()
        if provider == "yandex":
            try:
                text = await transcribe_yandex_speechkit(audio_bytes, filename, self.settings)
                return sanitize_stt_text(collapse_stt_repetition(text))
            except SttProviderError:
                raise
            except Exception:
                logger.warning("Yandex STT failed", exc_info=True)
                raise
        if provider == "openai":
            try:
                text = await transcribe_openai_whisper(audio_bytes, filename, self.settings)
                return sanitize_stt_text(collapse_stt_repetition(text))
            except SttProviderError:
                raise
            except Exception:
                logger.warning("OpenAI STT failed, fallback to local whisper", exc_info=True)

        max_bytes = self.settings.stt_max_audio_bytes
        if len(audio_bytes) > max_bytes and provider == "whisper":
            raise ValueError(
                f"Слишком длинная запись ({len(audio_bytes) // 1024} КБ). "
                "Нажимайте «Ответить» раз в 5–8 минут или включите STT_PROVIDER=yandex."
            )

        suffix = ".webm"
        if audio_bytes[:4] == b"\x1aE\xdf":
            suffix = ".webm"
        elif audio_bytes[:4] == b"OggS":
            suffix = ".ogg"
        elif len(audio_bytes) > 8 and audio_bytes[4:8] == b"ftyp":
            suffix = ".m4a"

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        t0 = time.perf_counter()
        try:
            async with self._whisper_lock:
                text = await asyncio.to_thread(self._transcribe_file, tmp_path)
                if not text.strip() and self.settings.stt_vad_filter:
                    logger.info("STT empty with VAD — retry without VAD (%d KB)", len(audio_bytes) // 1024)
                    text = await asyncio.to_thread(self._transcribe_file, tmp_path, use_vad=False)
            text = sanitize_stt_text(collapse_stt_repetition(text))
            logger.info(
                "STT %.2fs | %d KB | %d chars",
                time.perf_counter() - t0,
                len(audio_bytes) // 1024,
                len(text),
            )
            return text
        except SttUnavailableError:
            raise
        except Exception:
            logger.warning("STT failed", exc_info=True)
            return ""
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def tts_path(self, message_id: str) -> Path:
        engine = (self.settings.tts_engine or "silero").lower()
        if engine == "yandex":
            ext = ".mp3" if (self.settings.yandex_tts_format or "mp3").lower() == "mp3" else ".ogg"
            return self.tts_dir / f"{message_id}{ext}"
        ext = ".mp3" if engine == "edge" else ".wav"
        return self.tts_dir / f"{message_id}{ext}"

    def _resolve_tts_path(self, message_id: str) -> Path:
        names = [f"{message_id}.wav", f"{message_id}.mp3", f"{message_id}.ogg"]
        for name in names:
            path = self.tts_dir / name
            if path.exists() and path.stat().st_size > 0:
                return path
        return self.tts_path(message_id)

    async def text_to_speech(self, text: str, message_id: str | None = None) -> Path | None:
        """Синтез: yandex / edge-tts / Silero."""
        if not self.settings.tts_enabled:
            return None
        raw = text.strip()
        if not raw:
            return None

        mid = message_id or str(uuid.uuid4())
        existing = self._resolve_tts_path(mid)
        if existing.exists() and existing.stat().st_size > 0:
            return existing

        voice = self.settings.effective_tts_voice
        cleaned = prepare_for_tts(raw, voice)
        speak_text = cleaned or raw

        engine = (self.settings.tts_engine or "silero").lower()
        if engine == "yandex":
            out_mp3 = self.tts_dir / f"{mid}.mp3"
            try:
                ok = await asyncio.to_thread(
                    lambda: synthesize_yandex_mp3(speak_text, out_mp3, self.settings)
                )
                if ok:
                    return out_mp3
            except Exception:
                logger.warning("Yandex TTS failed, fallback Silero", exc_info=True)
        elif engine == "edge":
            out_mp3 = self.tts_dir / f"{mid}.mp3"
            try:
                if await synthesize_edge_mp3(speak_text, out_mp3, self.settings.tts_edge_voice):
                    return out_mp3
            except Exception:
                logger.warning("Edge TTS failed, fallback Silero", exc_info=True)

        if not cleaned:
            return None
        out_path = self.tts_dir / f"{mid}.wav"
        try:
            silero_voice = self.settings.tts_voice or "kseniya"
            ok = await asyncio.to_thread(
                lambda: synthesize_to_wav(cleaned, out_path, speaker=silero_voice)
            )
            if ok:
                return out_path
        except Exception as exc:
            logger.warning("Silero TTS failed: %s", exc, exc_info=True)
            out_path.unlink(missing_ok=True)
        return None

    @staticmethod
    def media_type_for(path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".mp3":
            return "audio/mpeg"
        if ext == ".ogg":
            return "audio/ogg"
        return "audio/wav"
