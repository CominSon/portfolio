import json
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect as StarletteWebSocketDisconnect

from app.api.deps import editor_manager, session_manager, voice_pipeline, ws_manager
from app.database import async_session_factory
logger = logging.getLogger(__name__)
ws_router = APIRouter()


async def _get_interview(db: AsyncSession, interview_id: str, token: str | None):
    try:
        iid = uuid.UUID(interview_id)
    except ValueError:
        return None
    if token:
        interview = await session_manager.get_by_token(db, token)
        if interview and str(interview.id) == interview_id:
            return interview
    return await session_manager.get_interview(db, iid)


async def _safe_send_json(websocket: WebSocket, payload: dict) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, StarletteWebSocketDisconnect):
        return False
    except Exception as exc:
        if "disconnect" in str(exc).lower() or "closed" in str(exc).lower():
            return False
        raise


@ws_router.websocket("/ws/interviews/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: str, token: str | None = None):
    await websocket.accept()
    async with async_session_factory() as db:
        interview = await _get_interview(db, interview_id, token)
        if not interview:
            await websocket.close(code=4004)
            return

        await ws_manager.connect(interview_id, websocket)
        role = "candidate" if token else "employer"
        if not await _safe_send_json(
            websocket,
            {
                "type": "connected",
                "interview_id": interview_id,
                "role": role,
                "editor_state": {
                    "content": interview.editor_content,
                    "language": interview.editor_language,
                    "version": interview.editor_version,
                    "seq": interview.editor_seq,
                },
            },
        ):
            ws_manager.disconnect(interview_id, websocket)
            return

        try:
            while True:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                mtype = msg.get("type", "")

                async with async_session_factory() as db_inner:
                    interview = await session_manager.get_interview(db_inner, uuid.UUID(interview_id))
                    if not interview:
                        break

                    if mtype in ("code_insert", "code_delete", "code_replace"):
                        actor = "candidate" if role == "candidate" else "ai"
                        seq, content, operation = await editor_manager.apply_and_persist(
                            db_inner,
                            interview,
                            actor,
                            mtype,
                            msg.get("range", {}),
                            msg.get("text", ""),
                        )
                        await db_inner.commit()
                        broadcast = {
                            "type": "code_applied",
                            "seq": seq,
                            "operation": operation,
                        }
                        await ws_manager.broadcast(interview_id, broadcast)

                    elif mtype == "cursor_move":
                        await ws_manager.broadcast(
                            interview_id,
                            {"type": "cursor_move", "position": msg.get("position"), "actor": role},
                            exclude=websocket,
                        )

                    elif mtype in (
                        "camera_enabled",
                        "camera_disabled",
                        "microphone_enabled",
                        "microphone_disabled",
                        "screenshare_started",
                        "screenshare_stopped",
                    ):
                        camera = interview.media_camera
                        mic = interview.media_microphone
                        screen = interview.media_screenshare
                        if mtype == "camera_enabled":
                            camera = True
                        elif mtype == "camera_disabled":
                            camera = False
                        elif mtype == "microphone_enabled":
                            mic = True
                        elif mtype == "microphone_disabled":
                            mic = False
                        elif mtype == "screenshare_started":
                            screen = True
                        elif mtype == "screenshare_stopped":
                            screen = False
                        await session_manager.update_media(db_inner, interview, camera, mic, screen)
                        await db_inner.commit()
                        await ws_manager.broadcast(interview_id, msg)
                        if interview.status == "active" and not session_manager.media_ready(interview):
                            await ws_manager.broadcast(
                                interview_id,
                                {
                                    "type": "interview_event",
                                    "event": "media_warning",
                                    "reason": mtype,
                                    "message": "Включите камеру, микрофон и демонстрацию экрана. Таймер продолжает идти.",
                                },
                            )

                    elif mtype == "sync_state":
                        await _safe_send_json(
                            websocket,
                            {
                                "type": "sync_state",
                                "editor_state": {
                                    "content": interview.editor_content,
                                    "language": interview.editor_language,
                                    "version": interview.editor_version,
                                    "seq": interview.editor_seq,
                                },
                            },
                        )

                    elif mtype == "submit_answer_ws":
                        text = msg.get("text", "")
                        answer_type = msg.get("answer_type", "voice")
                        turn = await session_manager.process_candidate_answer(
                            db_inner, interview, text, answer_type
                        )
                        ai_text = turn.get("message", "")
                        message_id = str(uuid.uuid4())
                        await db_inner.commit()

                        await ws_manager.broadcast(
                            interview_id,
                            {"type": "ai_typing", "active": True},
                        )
                        await ws_manager.broadcast(
                            interview_id,
                            {"type": "ai_message", "text": ai_text, "message_id": message_id},
                        )
                        audio_path = await voice_pipeline.text_to_speech(ai_text, message_id)
                        if audio_path:
                            await ws_manager.broadcast(
                                interview_id,
                                {"type": "ai_voice_started", "message_id": message_id},
                            )
                            await ws_manager.broadcast(
                                interview_id,
                                {
                                    "type": "ai_voice_finished",
                                    "message_id": message_id,
                                    "audio_url": f"/api/v1/interviews/{interview_id}/tts-audio/{message_id}",
                                },
                            )
                        await ws_manager.broadcast(
                            interview_id,
                            {"type": "ai_typing", "active": False},
                        )

                        for action in turn.get("code_actions", []):
                            op = action.get("action", "insert")
                            op_type = f"code_{op}" if op in ("insert", "replace", "delete") else "code_insert"
                            seq, _, operation = await editor_manager.apply_and_persist(
                                db_inner,
                                interview,
                                "ai",
                                op_type,
                                action.get("range", {}),
                                action.get("text", ""),
                            )
                            await db_inner.commit()
                            await ws_manager.broadcast(
                                interview_id,
                                {
                                    "type": "ai_code_action",
                                    "seq": seq,
                                    "operation": operation,
                                },
                            )

                    elif mtype in ("line_highlight", "inline_comment", "selection_change"):
                        await ws_manager.broadcast(interview_id, {**msg, "actor": role})

        except WebSocketDisconnect:
            pass
        except StarletteWebSocketDisconnect:
            pass
        finally:
            ws_manager.disconnect(interview_id, websocket)
