"""Локальный TTS Silero (русский, без Microsoft/Google)."""
import logging
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.services.tts_prepare import prepare_for_tts, split_sentences

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
_PAUSE_MS = 280

_model = None
_speakers: list[str] | None = None


def _load_model():
    global _model, _speakers
    if _model is not None:
        return _model, _speakers

    import torch

    logger.info("Загрузка Silero TTS (первый запуск может скачать модель с GitHub)...")
    model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-models",
        model="silero_tts",
        language="ru",
        speaker="v4_ru",
        trust_repo=True,
    )
    model.to(torch.device("cpu"))
    speakers = getattr(model, "speakers", None) or ["kseniya"]
    _model = model
    _speakers = list(speakers)
    logger.info("Silero TTS готов, голоса: %s", ", ".join(_speakers[:6]))
    return _model, _speakers


def _silence_ms(ms: int) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * ms / 1000), dtype=np.float32)


def _adjust_speed(audio: np.ndarray, speed: float) -> np.ndarray:
    if speed <= 0 or abs(speed - 1.0) < 0.02:
        return audio
    target_len = max(1, int(len(audio) / speed))
    x_old = np.linspace(0, 1, num=len(audio))
    x_new = np.linspace(0, 1, num=target_len)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def _synthesize_chunk(model, voice: str, chunk: str) -> np.ndarray:
    import torch

    audio = model.apply_tts(
        text=chunk,
        speaker=voice,
        sample_rate=SAMPLE_RATE,
        put_accent=True,
        put_yo=True,
    )
    if isinstance(audio, torch.Tensor):
        audio = audio.cpu().numpy()
    return np.asarray(audio, dtype=np.float32)


def synthesize_to_wav(text: str, out_path: Path, speaker: str | None = None) -> bool:
    import soundfile as sf

    settings = get_settings()
    raw = text.strip()
    if not raw:
        return False

    model, speakers = _load_model()
    voice = (speaker or settings.tts_voice or "kseniya").lower()
    if voice not in speakers:
        for fallback in ("kseniya", "baya", "xenia", "aidar"):
            if fallback in speakers:
                voice = fallback
                break
        else:
            voice = speakers[0]

    prepared = prepare_for_tts(raw, voice)
    sentences = split_sentences(prepared) or [prepared]
    logger.info(
        "TTS: voice=%s speed=%.2f sentences=%d chars=%d",
        voice,
        settings.tts_speed,
        len(sentences),
        len(prepared),
    )

    chunks: list[np.ndarray] = []
    pause = _silence_ms(_PAUSE_MS)
    for i, sentence in enumerate(sentences):
        if len(sentence) < 2:
            continue
        try:
            part = _synthesize_chunk(model, voice, sentence)
            part = _adjust_speed(part, settings.tts_speed)
            chunks.append(part)
            if i < len(sentences) - 1:
                chunks.append(pause)
        except Exception as exc:
            logger.warning("TTS chunk failed (%s): %s", sentence[:40], exc)

    if not chunks:
        return False

    audio = np.concatenate(chunks)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), audio, SAMPLE_RATE)
    ok = out_path.exists() and out_path.stat().st_size > 0
    if ok:
        logger.info("TTS saved: %s (%d bytes)", out_path.name, out_path.stat().st_size)
    return ok
