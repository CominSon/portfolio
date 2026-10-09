#!/usr/bin/env python3
"""Монтаж итогового видео интервью (ffmpeg)."""
import argparse
import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select

from app.config import get_settings
from app.database import async_session_factory
from app.models.entities import Interview
from app.services.video_montage import MontageInputs, build_montage, paths_for_interview


async def load_inputs(interview_id: UUID) -> tuple[MontageInputs, float | None]:
    settings = get_settings()
    paths = paths_for_interview(Path(settings.recordings_dir), interview_id)
    async with async_session_factory() as db:
        inv = (
            await db.execute(select(Interview).where(Interview.id == interview_id))
        ).scalar_one_or_none()
        if not inv:
            raise SystemExit(f"Интервью {interview_id} не найдено")

        max_d: float | None = None
        if inv.started_at and inv.ended_at:
            from datetime import timezone

            a = inv.ended_at if inv.ended_at.tzinfo else inv.ended_at.replace(tzinfo=timezone.utc)
            b = inv.started_at if inv.started_at.tzinfo else inv.started_at.replace(tzinfo=timezone.utc)
            max_d = max(30.0, (a - b).total_seconds() + 45.0)
    return paths, max_d


async def main() -> None:
    parser = argparse.ArgumentParser(description="Смонтировать видео интервью")
    parser.add_argument("interview_id", nargs="?", help="UUID интервью (по умолчанию — последнее)")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Выходной MP4 (по умолчанию exports/video_<id>.mp4)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=None,
        help="Ограничить длительность итога (сек), поверх длительности сессии",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать выходной файл, если уже существует",
    )
    args = parser.parse_args()

    if args.interview_id:
        uid = (
            UUID(args.interview_id.replace("-", ""))
            if len(args.interview_id) == 32
            else UUID(args.interview_id)
        )
    else:
        async with async_session_factory() as db:
            inv = (
                await db.execute(
                    select(Interview)
                    .where(Interview.status.in_(("report_ready", "completed", "completing")))
                    .order_by(Interview.ended_at.desc().nullslast())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if not inv:
                raise SystemExit("Нет завершённых интервью")
            uid = inv.id
            print(f"Последнее интервью: {uid}")

    inputs, max_d = await load_inputs(uid)
    if args.max_duration:
        max_d = min(max_d or args.max_duration, args.max_duration)
    if max_d:
        print(f"Длительность монтажа: ~{int(max_d)} с")

    out = args.output or (ROOT / "exports" / f"video_{uid.hex}.mp4")
    if args.force and out.is_file():
        out.unlink()

    if not inputs.audio or not inputs.audio.is_file():
        print(
            "Предупреждение: нет отдельной записи микрофона (audio/recording.webm). "
            "Итог может быть без звука."
        )

    print(f"Screen: {inputs.screen}")
    print(f"Camera: {inputs.camera}")
    print(f"Audio:  {inputs.audio or '—'}")
    print(f"→ {out}")

    build_montage(inputs, out, max_duration_sec=max_d)
    print(f"Готово: {out}")


if __name__ == "__main__":
    asyncio.run(main())
