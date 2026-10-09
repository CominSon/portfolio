import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Interview
from app.services.code_operations_manager import CodeOperationsManager
from app.services.code_timeline_manager import CodeTimelineManager


class CollaborativeEditorManager:
    def __init__(self) -> None:
        self.code_ops = CodeOperationsManager()
        self.timeline = CodeTimelineManager()

    async def apply_and_persist(
        self,
        db: AsyncSession,
        interview: Interview,
        actor: str,
        op_type: str,
        range_data: dict,
        text: str = "",
    ) -> tuple[int, str, dict]:
        before = interview.editor_content
        after = self.code_ops.apply_operation(before, op_type, range_data, text)
        interview.editor_seq += 1
        seq = interview.editor_seq
        interview.editor_content = after
        interview.editor_version += 1

        action = op_type.replace("code_", "") + "_code"
        await self.timeline.log_code_operation(
            db, interview.id, seq, actor, action, range_data, before, after
        )
        lines = f"{range_data.get('startLine', '')}-{range_data.get('endLine', '')}"
        await self.timeline.log_editor_event(
            db, interview.id, actor, action, lines=lines, payload={"text_len": len(text)}
        )

        operation = {
            "action": action,
            "actor": actor,
            "range": range_data,
            "before": before,
            "after": after,
        }
        return seq, after, operation
