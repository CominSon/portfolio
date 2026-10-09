from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import CompetencyItem


class InterviewCreate(BaseModel):
    employer_id: UUID
    candidate_email: EmailStr | None = None
    candidate_name: str | None = None  # ФИО вручную, если резюме не загружено
    feedback_emails: list[EmailStr] = Field(default_factory=list)
    template_id: UUID | None = None
    job_description_text: str | None = None
    resume_text: str | None = None


class InterviewFormatUpdate(BaseModel):
    format_selection_mode: str = "auto"
    allowed_formats: list[str] = Field(default_factory=list)
    selected_format: str | None = None
    live_coding_ai_assistant: bool = False
    # Временно в админке: тестовый прогон (N ответов) или полное интервью (~60 мин)
    session_mode: str = "test"  # test | full
    test_max_turns: int | None = Field(default=None, ge=1, le=20)


class CompetenciesUpdate(BaseModel):
    competencies: list[CompetencyItem]


class GenerateLinkRequest(BaseModel):
    """Origin UI, с которого открыта админка (например quick tunnel trycloudflare.com)."""
    frontend_origin: str | None = None


class MediaStatusUpdate(BaseModel):
    camera_enabled: bool
    microphone_enabled: bool
    screenshare_enabled: bool


class SubmitAnswerRequest(BaseModel):
    answer_type: str = Field(pattern="^(voice|code|combined)$")
    text: str | None = None
    editor_content: str | None = None


class TranscriptItem(BaseModel):
    speaker: str
    text: str


class WarmupQuizQuestion(BaseModel):
    id: str
    skill: str
    question: str
    options: list[str]


class WarmupQuizAnswerRequest(BaseModel):
    question_id: str
    selected_index: int = Field(ge=-1, le=3)
    timed_out: bool = False


class InterviewResponse(BaseModel):
    id: UUID
    status: str
    access_token: str
    candidate_link: str | None = None
    selected_format: str | None
    allowed_formats: list[str]
    format_selection_mode: str
    duration_minutes: int
    editor_language: str
    editor_content: str
    media_camera: bool
    media_microphone: bool
    media_screenshare: bool
    competencies: list[CompetencyItem] = Field(default_factory=list)
    feedback_emails: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    transcripts: list[TranscriptItem] = Field(default_factory=list)
    briefing_text: str | None = None
    briefing_audio_url: str | None = None
    warmup_quiz: list[WarmupQuizQuestion] = Field(default_factory=list)
    live_coding_ai_assistant: bool = False
    sql_dialect: str | None = None
    session_mode: str = "full"
    test_max_turns: int | None = None
    candidate_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    competency_scores: dict
    strengths: list
    weaknesses: list
    communication_assessment: dict
    code_quality_assessment: dict
    honesty_signals: dict
    confidence_level: float
    recommendation: str
    recommendation_ru: str = ""
    final_summary: str
    report_text: str = ""

    model_config = {"from_attributes": True}
