"""Синтез речи через Yandex SpeechKit TTS (облако, естественные русские голоса)."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from app.services.tts_prepare import split_sentences

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger(__name__)

TTS_URL = "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize"
# Лимит API ~5000 символов; режем по предложениям с запасом.
_MAX_CHUNK_CHARS = 4000


class TtsProviderError(Exception):
    """Yandex TTS недоступен или вернул ошибку."""


def _credentials(settings: Settings) -> tuple[str, str]:
    folder_id = (settings.yandex_folder_id or "").strip()
    api_key = (settings.yandex_api_key or "").strip()
    if not folder_id or not api_key:
        raise TtsProviderError(
            "Для TTS_ENGINE=yandex задайте YANDEX_FOLDER_ID и YANDEX_API_KEY в .env"
        )
    return folder_id, api_key


def _split_for_yandex(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if len(cleaned) <= _MAX_CHUNK_CHARS:
        return [cleaned]

    sentences = split_sentences(cleaned) or [cleaned]
    chunks: list[str] = []
    buf = ""
    for sentence in sentences:
        if len(sentence) > _MAX_CHUNK_CHARS:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            for i in range(0, len(sentence), _MAX_CHUNK_CHARS):
                chunks.append(sentence[i : i + _MAX_CHUNK_CHARS].strip())
            continue
        candidate = f"{buf} {sentence}".strip() if buf else sentence
        if len(candidate) <= _MAX_CHUNK_CHARS:
            buf = candidate
        else:
            if buf:
                chunks.append(buf.strip())
            buf = sentence
    if buf.strip():
        chunks.append(buf.strip())
    return chunks or [cleaned[:_MAX_CHUNK_CHARS]]


def _synthesize_chunk(
    text: str,
    *,
    folder_id: str,
    api_key: str,
    lang: str,
    voice: str,
    speed: float,
    emotion: str | None,
    audio_format: str,
    timeout_sec: float,
) -> bytes:
    data: dict[str, str] = {
        "text": text,
        "lang": lang,
        "voice": voice,
        "folderId": folder_id,
        "format": audio_format,
        "speed": str(speed),
    }
    if emotion:
        data["emotion"] = emotion
    if audio_format == "lpcm":
        data["sampleRateHertz"] = "48000"

    headers = {"Authorization": f"Api-Key {api_key}"}
    with httpx.Client(timeout=timeout_sec) as client:
        resp = client.post(TTS_URL, headers=headers, data=data)
    if resp.status_code >= 400:
        detail = resp.text[:400]
        raise TtsProviderError(f"Yandex TTS HTTP {resp.status_code}: {detail}")
    if not resp.content:
        raise TtsProviderError("Yandex TTS вернул пустой ответ")
    return resp.content


def _concat_mp3(parts: list[Path], out_path: Path) -> bool:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise TtsProviderError("Для склейки длинного TTS нужен ffmpeg в PATH")
    if len(parts) == 1:
        shutil.copy(parts[0], out_path)
        return out_path.exists() and out_path.stat().st_size > 0

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as lst:
        list_path = Path(lst.name)
        for part in parts:
            lst.write(f"file '{part.resolve()}'\n")

    try:
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-c",
                "copy",
                str(out_path),
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "")[-500:]
            raise TtsProviderError(f"ffmpeg не склеил TTS: {tail}")
        return out_path.exists() and out_path.stat().st_size > 0
    finally:
        list_path.unlink(missing_ok=True)


def synthesize_yandex_mp3(text: str, out_path: Path, settings: Settings) -> bool:
    """Синхронный синтез в MP3 (вызывать из asyncio.to_thread)."""
    raw = text.strip()
    if not raw:
        return False

    folder_id, api_key = _credentials(settings)
    lang = (settings.yandex_tts_lang or "ru-RU").strip() or "ru-RU"
    voice = (settings.yandex_tts_voice or "alena").strip() or "alena"
    audio_format = (settings.yandex_tts_format or "mp3").strip().lower() or "mp3"
    if audio_format not in ("mp3", "oggopus", "lpcm"):
        audio_format = "mp3"
    timeout = settings.yandex_tts_timeout_sec
    emotion = (settings.yandex_tts_emotion or "").strip() or None

    speed = settings.yandex_tts_speed
    if speed <= 0:
        speed = settings.tts_speed if settings.tts_speed > 0 else 1.0
    speed = max(0.1, min(3.0, speed))

    chunks_text = _split_for_yandex(raw)
    tmp_parts: list[Path] = []
    try:
        for i, chunk in enumerate(chunks_text):
            audio = _synthesize_chunk(
                chunk,
                folder_id=folder_id,
                api_key=api_key,
                lang=lang,
                voice=voice,
                speed=speed,
                emotion=emotion,
                audio_format=audio_format,
                timeout_sec=timeout,
            )
            with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
                part_path = Path(tmp.name)
                part_path.write_bytes(audio)
            tmp_parts.append(part_path)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        if audio_format == "mp3":
            ok = _concat_mp3(tmp_parts, out_path)
        elif len(tmp_parts) == 1:
            shutil.copy(tmp_parts[0], out_path)
            ok = out_path.exists() and out_path.stat().st_size > 0
        else:
            # oggopus / lpcm — склеиваем через ffmpeg в целевой контейнер
            ext = ".ogg" if audio_format == "oggopus" else ".wav"
            if out_path.suffix.lower() != ext:
                out_path = out_path.with_suffix(ext)
            ok = _concat_mp3(tmp_parts, out_path)

        if ok:
            logger.info(
                "Yandex TTS saved: %s voice=%s speed=%.2f chunks=%d (%d bytes)",
                out_path.name,
                voice,
                speed,
                len(chunks_text),
                out_path.stat().st_size,
            )
        return ok
    finally:
        for part in tmp_parts:
            part.unlink(missing_ok=True)
