import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Transcript


class TranscriptManager:
    async def add_entry(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        speaker: str,
        text: str,
        offset_ms: int | None = None,
    ) -> Transcript:
        entry = Transcript(
            interview_id=interview_id,
            speaker=speaker,
            text=text,
            offset_ms=offset_ms,
        )
        db.add(entry)
        return entry

    async def get_history(self, db: AsyncSession, interview_id: uuid.UUID, limit: int = 100) -> list[dict]:
        result = await db.execute(
            select(Transcript)
            .where(Transcript.interview_id == interview_id)
            .order_by(Transcript.created_at)
            .limit(limit)
        )
        rows = result.scalars().all()
        return [
            {"speaker": r.speaker, "text": r.text, "offset_ms": r.offset_ms, "created_at": r.created_at.isoformat()}
            for r in rows
        ]
