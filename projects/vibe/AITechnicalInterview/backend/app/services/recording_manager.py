import uuid
from pathlib import Path

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.entities import RecordingMetadata


class RecordingManager:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_dir = Path(self.settings.recordings_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _stream_path(self, interview_id: uuid.UUID, stream_type: str) -> Path:
        d = self.base_dir / str(interview_id) / stream_type
        d.mkdir(parents=True, exist_ok=True)
        return d / "recording.webm"

    def recording_path(self, interview_id: uuid.UUID, stream_type: str) -> Path:
        return self._stream_path(interview_id, stream_type)

    def montage_path(self, interview_id: uuid.UUID) -> Path:
        return self.base_dir / str(interview_id) / "montage.mp4"

    async def save_chunk(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        stream_type: str,
        chunk_index: int,
        data: bytes,
    ) -> RecordingMetadata:
        path = self._stream_path(interview_id, stream_type)
        mode = "ab" if chunk_index > 0 else "wb"
        async with aiofiles.open(path, mode) as f:
            await f.write(data)

        # Метаданные в SQLite — не на каждый чанк: снижает contention с submit-answer.
        touch_db = chunk_index < 2 or chunk_index % 10 == 0
        result = await db.execute(
            select(RecordingMetadata).where(
                RecordingMetadata.interview_id == interview_id,
                RecordingMetadata.stream_type == stream_type,
            )
        )
        meta = result.scalar_one_or_none()
        if meta is None:
            meta = RecordingMetadata(
                interview_id=interview_id,
                stream_type=stream_type,
                file_path=str(path),
                chunk_count=chunk_index + 1,
            )
            db.add(meta)
        elif touch_db:
            meta.chunk_count = chunk_index + 1
        else:
            # Без UPDATE — только файл на диске; chunk_count подтянется следующим touch.
            meta.chunk_count = max(meta.chunk_count or 0, chunk_index + 1)
            db.expunge(meta)
        return meta
