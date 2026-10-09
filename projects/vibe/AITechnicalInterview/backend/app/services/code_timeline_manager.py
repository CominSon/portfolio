import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import CodeOperation, EditorEvent


class CodeTimelineManager:
    async def log_editor_event(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        actor: str,
        action: str,
        lines: str | None = None,
        payload: dict | None = None,
    ) -> EditorEvent:
        event = EditorEvent(
            interview_id=interview_id,
            timestamp=datetime.utcnow(),
            actor=actor,
            action=action,
            lines=lines,
            payload=payload or {},
        )
        db.add(event)
        return event

    async def log_code_operation(
        self,
        db: AsyncSession,
        interview_id: uuid.UUID,
        seq: int,
        actor: str,
        action: str,
        range_data: dict,
        text_before: str | None,
        text_after: str | None,
    ) -> CodeOperation:
        op = CodeOperation(
            interview_id=interview_id,
            seq=seq,
            actor=actor,
            action=action,
            range_data=range_data,
            text_before=text_before,
            text_after=text_after,
        )
        db.add(op)
        return op
