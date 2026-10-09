"""Сборка итогового MP4 после интервью."""
from __future__ import annotations

import asyncio
import logging
from datetime import timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.entities import Interview
from app.services.video_montage import MontageInputs, build_montage, paths_for_interview

logger = logging.getLogger(__name__)


def montage_output_path(interview_id: UUID) -> Path:
    return Path(get_settings().recordings_dir) / str(interview_id) / "montage.mp4"


def mp4_looks_complete(path: Path, *, min_size: int = 10_000) -> bool:
    """True только если файл достаточно большой и содержит atom `moov` (иначе плеер видит «пустое» видео)."""
    try:
        if not path.is_file() or path.stat().st_size < min_size:
            return False
        # moov обычно в конце (или в начале при +faststart); читаем хвост + начало
        size = path.stat().st_size
        with path.open("rb") as f:
            head = f.read(min(256 * 1024, size))
            if size > 512 * 1024:
                f.seek(max(0, size - 512 * 1024))
                tail = f.read()
            else:
                tail = b""
        data = head + tail
        return b"moov" in data
    except OSError:
        return False


def montage_is_ready(interview_id: UUID) -> bool:
    return mp4_looks_complete(montage_output_path(interview_id))


async def load_montage_inputs(db: AsyncSession, interview_id: UUID) -> tuple[MontageInputs, float | None]:
    result = await db.execute(select(Interview).where(Interview.id == interview_id))
    inv = result.scalar_one_or_none()
    if not inv:
        raise ValueError(f"Interview {interview_id} not found")

    paths = paths_for_interview(Path(get_settings().recordings_dir), interview_id)

    max_d: float | None = None
    if inv.started_at and inv.ended_at:
        a = inv.ended_at if inv.ended_at.tzinfo else inv.ended_at.replace(tzinfo=timezone.utc)
        b = inv.started_at if inv.started_at.tzinfo else inv.started_at.replace(tzinfo=timezone.utc)
        max_d = max(30.0, (a - b).total_seconds() + 45.0)

    return paths, max_d


async def build_interview_montage(
    db: AsyncSession,
    interview_id: UUID,
    *,
    force_rebuild: bool = False,
) -> Path | None:
    """Собрать montage.mp4 в папке интервью. Блокирующий ffmpeg — в thread pool."""
    settings = get_settings()
    if not getattr(settings, "montage_enabled", True):
        logger.info("montage disabled interview=%s", interview_id)
        return None

    out = montage_output_path(interview_id)
    force = force_rebuild or getattr(settings, "montage_force_rebuild", False)
    if mp4_looks_complete(out) and not force:
        logger.info("montage already exists: %s", out)
        return out
    if out.is_file() and not mp4_looks_complete(out):
        logger.warning("incomplete montage cached at %s — will rebuild", out)
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass

    try:
        inputs, max_d = await load_montage_inputs(db, interview_id)
    except ValueError:
        logger.warning("montage: interview %s not found", interview_id)
        return None

    if not inputs.screen.is_file() or not inputs.camera.is_file():
        logger.warning(
            "montage skipped interview=%s (screen=%s camera=%s)",
            interview_id,
            inputs.screen.is_file(),
            inputs.camera.is_file(),
        )
        return None

    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / ".montage_work"
    try:
        await asyncio.to_thread(
            build_montage,
            inputs,
            out,
            work_dir=work,
            max_duration_sec=max_d,
        )
        if mp4_looks_complete(out):
            logger.info("montage ready interview=%s size=%s", interview_id, out.stat().st_size)
            return out
        if out.is_file():
            logger.error(
                "montage incomplete (no moov) interview=%s size=%s — removing",
                interview_id,
                out.stat().st_size,
            )
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
    except Exception:
        logger.exception("montage failed interview=%s", interview_id)
    return None
