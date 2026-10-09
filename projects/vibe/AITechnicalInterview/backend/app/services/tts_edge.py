"""TTS через Microsoft Edge (edge-tts): быстрее Silero, ru+en в одном голосе."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def synthesize_edge_mp3(text: str, out_path: Path, voice: str) -> bool:
    try:
        import edge_tts
    except ImportError:
        logger.warning("edge-tts не установлен: pip install edge-tts")
        return False

    cleaned = text.strip()
    if not cleaned:
        return False

    try:
        communicate = edge_tts.Communicate(cleaned, voice)
        await communicate.save(str(out_path))
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        logger.warning("Edge TTS failed", exc_info=True)
        return False
