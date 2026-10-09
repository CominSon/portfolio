from app.services.collaborative_editor_manager import CollaborativeEditorManager
from app.services.interview_session_manager import InterviewSessionManager
from app.services.recording_manager import RecordingManager
from app.services.voice_pipeline import VoicePipeline
from app.services.websocket_manager import WebSocketManager

voice_pipeline = VoicePipeline()
session_manager = InterviewSessionManager(voice_pipeline=voice_pipeline)
editor_manager = CollaborativeEditorManager()
recording_manager = RecordingManager()
ws_manager = WebSocketManager()
