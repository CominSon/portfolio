"""Очистка временных файлов после интервью (MVP: экономия диска и RAM)."""
import logging
import shutil
from pathlib import Path
from uuid import UUID

from app.config import get_settings

logger = logging.getLogger(__name__)

KEEP_STREAMS = frozenset({"camera", "screen", "microphone", "audio"})


def cleanup_after_interview(interview_id: UUID) -> None:
    """Удалить TTS этого интервью; оставить camera/screen webm и данные в БД."""
    settings = get_settings()
    base = Path(settings.recordings_dir)
    interview_dir = base / str(interview_id)
    iid = str(interview_id)

    # TTS переносим в папку интервью (для монтажа), глобальные файлы удаляем
    tts_dir = base / "tts"
    archive = interview_dir / "tts"
    archive.mkdir(parents=True, exist_ok=True)
    moved_tts = 0
    if tts_dir.is_dir():
        for path in tts_dir.iterdir():
            if not path.is_file():
                continue
            name = path.name
            if iid in name or name.startswith(f"briefing-{iid}") or name.startswith(f"farewell-{iid}"):
                dest = archive / path.name
                try:
                    if dest.exists():
                        dest.unlink()
                    path.rename(dest)
                    moved_tts += 1
                except OSError as exc:
                    logger.warning("archive tts %s: %s", path, exc)

    if interview_dir.is_dir():
        for child in interview_dir.iterdir():
            if child.is_dir() and child.name == ".montage_work":
                shutil.rmtree(child, ignore_errors=True)
                continue
            if child.is_dir() and child.name not in KEEP_STREAMS:
                for f in child.rglob("*"):
                    if f.is_file():
                        try:
                            f.unlink()
                        except OSError:
                            pass
                try:
                    child.rmdir()
                except OSError:
                    pass

    logger.info(
        "cleanup interview=%s: archived %d tts files to %s, kept streams",
        interview_id,
        moved_tts,
        interview_dir,
    )
