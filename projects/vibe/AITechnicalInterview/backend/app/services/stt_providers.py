"""Провайдеры STT: faster-whisper, OpenAI Whisper API, Yandex SpeechKit."""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

STT_SYNC_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"


class SttProviderError(Exception):
    """STT провайдер недоступен или вернул ошибку."""


async def transcribe_openai_whisper(
    audio_bytes: bytes,
    filename: str,
    settings: Settings,
) -> str:
    """OpenAI / совместимый API: whisper-1, хорошо для длинных ответов на русском."""
    api_key = (settings.openai_stt_api_key or settings.llm_api_key or "").strip()
    if not api_key:
        raise SttProviderError(
            "Для STT_PROVIDER=openai нужен OPENAI_STT_API_KEY или LLM_API_KEY (OpenAI)."
        )
    base = (settings.openai_stt_base_url or "https://api.openai.com/v1").rstrip("/")
    model = settings.openai_stt_model or "whisper-1"
    language = settings.stt_language or "ru"
    prompt = (settings.stt_initial_prompt or "").strip() or None

    data: dict[str, str] = {"model": model, "language": language, "response_format": "json"}
    if prompt:
        data["prompt"] = prompt[:800]

    async with httpx.AsyncClient(timeout=settings.openai_stt_timeout_sec) as client:
        resp = await client.post(
            f"{base}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, audio_bytes)},
            data=data,
        )
        if resp.status_code >= 400:
            detail = resp.text[:300]
            raise SttProviderError(f"OpenAI STT HTTP {resp.status_code}: {detail}")
        payload = resp.json()
        text = str(payload.get("text") or "").strip()
        logger.info("OpenAI STT ok | %d KB | %d chars", len(audio_bytes) // 1024, len(text))
        return text


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SttProviderError("Для STT_PROVIDER=yandex нужен ffmpeg в PATH (sudo apt install ffmpeg).")
    return ffmpeg


def _require_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise SttProviderError("Для STT_PROVIDER=yandex нужен ffprobe (пакет ffmpeg).")
    return ffprobe


def _yandex_credentials(settings: Settings) -> tuple[str, str]:
    folder_id = (settings.yandex_folder_id or "").strip()
    api_key = (settings.yandex_api_key or "").strip()
    if not folder_id or not api_key:
        raise SttProviderError(
            "Для STT_PROVIDER=yandex задайте YANDEX_FOLDER_ID и YANDEX_API_KEY в .env"
        )
    return folder_id, api_key


def _media_duration_seconds(path: Path) -> float:
    ffprobe = _require_ffprobe()
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        raw = (proc.stdout or "").strip()
        if raw and raw.upper() != "N/A":
            try:
                val = float(raw)
                if val > 0:
                    return val
            except ValueError:
                pass

    # MediaRecorder webm часто без duration в заголовке — парсим вывод ffmpeg
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        proc = subprocess.run(
            [ffmpeg, "-i", str(path)],
            capture_output=True,
            text=True,
        )
        m = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", proc.stderr or "")
        if m:
            h, mi, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
            total = h * 3600 + mi * 60 + sec
            if total > 0:
                return total
    return 0.0


def _estimate_duration_from_size(path: Path, *, chunk_seconds: float) -> float:
    """Грубая оценка, если метаданных нет (типичный opus/webm ~28–40 КБ/с)."""
    size = path.stat().st_size
    if size <= 0:
        return chunk_seconds
    # 20 КБ/с — консервативно для webm/opus (чтобы не обрезать длинную речь)
    estimated = size / 20_000.0
    return max(chunk_seconds, min(estimated, 7200.0))


def _convert_to_ogg_opus(
    src: Path,
    dst: Path,
    *,
    offset_seconds: float = 0,
    max_seconds: float | None = None,
) -> None:
    ffmpeg = _require_ffmpeg()
    cmd = [ffmpeg, "-y"]
    if offset_seconds > 0:
        cmd.extend(["-ss", str(offset_seconds)])
    cmd.extend(["-i", str(src), "-vn", "-ac", "1", "-ar", "48000", "-c:a", "libopus"])
    if max_seconds and max_seconds > 0:
        cmd.extend(["-t", str(max_seconds)])
    cmd.append(str(dst))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-500:]
        raise SttProviderError(f"ffmpeg не сконвертировал аудио: {tail}")


def _recognize_yandex_sync(
  audio_bytes: bytes,
  *,
  folder_id: str,
  api_key: str,
  lang: str,
  topic: str | None,
  timeout_sec: float,
) -> str:
    params: dict[str, str] = {
        "folderId": folder_id,
        "lang": lang,
        "format": "oggopus",
    }
    if topic:
        params["topic"] = topic
    headers = {"Authorization": f"Api-Key {api_key}"}
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(STT_SYNC_URL, params=params, headers=headers, content=audio_bytes)
    if resp.status_code >= 400:
        detail = resp.text[:400]
        raise SttProviderError(f"Yandex STT HTTP {resp.status_code}: {detail}")
    try:
        payload = resp.json()
    except Exception:
        return resp.text.strip()
    if isinstance(payload, dict):
        if payload.get("error_code"):
            raise SttProviderError(str(payload.get("error_message") or payload))
        return str(payload.get("result") or "").strip()
    return str(payload).strip()


def _transcribe_yandex_path(path: Path, settings: Settings) -> str:
    folder_id, api_key = _yandex_credentials(settings)
    lang = (settings.yandex_stt_lang or "ru-RU").strip() or "ru-RU"
    topic = (settings.yandex_stt_topic or "").strip() or None
    timeout = settings.yandex_stt_timeout_sec
    chunk = max(10.0, float(settings.yandex_stt_chunk_seconds or 25))
    max_chunks = max(1, int(settings.yandex_stt_max_chunks or 120))

    duration = _media_duration_seconds(path)
    size_hint = _estimate_duration_from_size(path, chunk_seconds=chunk)
    if duration <= 0:
        duration = size_hint
    else:
        duration = max(duration, size_hint)

    parts: list[str] = []
    offset = 0.0
    chunk_index = 0
    empty_streak = 0

    while chunk_index < max_chunks:
        seg_len = chunk
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            ogg_path = Path(tmp.name)
        try:
            _convert_to_ogg_opus(path, ogg_path, offset_seconds=offset, max_seconds=seg_len)
            audio = ogg_path.read_bytes()
            if len(audio) < 200:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                offset += seg_len
                chunk_index += 1
                continue
            empty_streak = 0
            text = _recognize_yandex_sync(
                audio,
                folder_id=folder_id,
                api_key=api_key,
                lang=lang,
                topic=topic,
                timeout_sec=timeout,
            )
            if text:
                parts.append(text)
        finally:
            ogg_path.unlink(missing_ok=True)
        offset += seg_len
        chunk_index += 1

    result = " ".join(parts).strip()
    logger.info(
        "Yandex STT ok | %s | est %.0fs | %d chunks | %d chars",
        path.name,
        duration,
        chunk_index,
        len(result),
    )
    return result


async def transcribe_yandex_speechkit(
    audio_bytes: bytes,
    filename: str,
    settings: Settings,
) -> str:
    suffix = Path(filename or "answer.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        src = Path(tmp.name)
    try:
        import asyncio

        return await asyncio.to_thread(_transcribe_yandex_path, src, settings)
    finally:
        src.unlink(missing_ok=True)


async def transcribe_yandex_speechkit_from_path(path: str, settings: Settings) -> str:
    import asyncio

    return await asyncio.to_thread(_transcribe_yandex_path, Path(path), settings)
