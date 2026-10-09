import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class InterviewStatus(str, enum.Enum):
    CREATED = "created"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    COMPETENCIES_CONFIRMED = "competencies_confirmed"
    FORMAT_SELECTED = "format_selected"
    SESSION_LINK_GENERATED = "session_link_generated"
    CANDIDATE_JOINED = "candidate_joined"
    MEDIA_PRECHECK = "media_precheck"
    READY = "ready"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETING = "completing"
    COMPLETED = "completed"
    REPORT_READY = "report_ready"


class InterviewFormat(str, enum.Enum):
    LIVE_CODING = "Live Coding"
    CODE_REVIEW = "Code Review"
    ARCHITECTURE = "Architecture Interview"
    AI_ASSISTED = "AI-Assisted Interview"


class FormatSelectionMode(str, enum.Enum):
    AUTO = "auto"
    RESTRICTED = "restricted"
    MANUAL = "manual"


class Recommendation(str, enum.Enum):
    REJECT = "reject"
    WEAK_FIT = "weak_fit"
    GOOD_FIT = "good_fit"
    STRONG_FIT = "strong_fit"


class Employer(Base):
    __tablename__ = "employers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    contact_emails: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interviews: Mapped[list["Interview"]] = relationship(back_populates="employer")
    templates: Mapped[list["InterviewTemplate"]] = relationship(back_populates="employer")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    resume_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interviews: Mapped[list["Interview"]] = relationship(back_populates="candidate")


class InterviewTemplate(Base):
    __tablename__ = "interview_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    job_description_text: Mapped[str | None] = mapped_column(Text)
    format_selection_mode: Mapped[str] = mapped_column(String(32), default=FormatSelectionMode.AUTO.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer: Mapped["Employer"] = relationship(back_populates="templates")
    competencies: Mapped[list["TemplateCompetency"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )
    settings: Mapped["TemplateSettings | None"] = relationship(
        back_populates="template", uselist=False, cascade="all, delete-orphan"
    )
    allowed_formats: Mapped[list["TemplateAllowedFormat"]] = relationship(
        back_populates="template", cascade="all, delete-orphan"
    )


class TemplateCompetency(Base):
    __tablename__ = "template_competencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_templates.id"), nullable=False)
    skill: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=10)
    source: Mapped[str] = mapped_column(String(32), default="manual")

    template: Mapped["InterviewTemplate"] = relationship(back_populates="competencies")


class TemplateSettings(Base):
    __tablename__ = "template_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_templates.id"), unique=True)
    ai_behavior: Mapped[dict] = mapped_column(JSON, default=dict)
    scoring_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    evaluation_priorities: Mapped[list] = mapped_column(JSON, default=list)
    interview_mode_settings: Mapped[dict] = mapped_column(JSON, default=dict)

    template: Mapped["InterviewTemplate"] = relationship(back_populates="settings")


class TemplateAllowedFormat(Base):
    __tablename__ = "template_allowed_formats"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    template_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interview_templates.id"), nullable=False)
    format_name: Mapped[str] = mapped_column(String(64), nullable=False)

    template: Mapped["InterviewTemplate"] = relationship(back_populates="allowed_formats")


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    employer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employers.id"), nullable=False)
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("candidates.id"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("interview_templates.id"))
    status: Mapped[str] = mapped_column(String(32), default=InterviewStatus.CREATED.value)
    access_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    job_description_text: Mapped[str | None] = mapped_column(Text)
    resume_text: Mapped[str | None] = mapped_column(Text)
    format_selection_mode: Mapped[str] = mapped_column(String(32), default=FormatSelectionMode.AUTO.value)
    allowed_formats: Mapped[list] = mapped_column(JSON, default=list)
    selected_format: Mapped[str | None] = mapped_column(String(64))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    editor_language: Mapped[str] = mapped_column(String(32), default="python")
    editor_content: Mapped[str] = mapped_column(Text, default="")
    editor_version: Mapped[int] = mapped_column(Integer, default=0)
    editor_seq: Mapped[int] = mapped_column(Integer, default=0)
    ai_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    feedback_emails: Mapped[list] = mapped_column(JSON, default=list)
    media_camera: Mapped[bool] = mapped_column(Boolean, default=False)
    media_microphone: Mapped[bool] = mapped_column(Boolean, default=False)
    media_screenshare: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employer: Mapped["Employer"] = relationship(back_populates="interviews")
    candidate: Mapped["Candidate | None"] = relationship(back_populates="interviews")
    competencies: Mapped[list["Competency"]] = relationship(
        back_populates="interview", cascade="all, delete-orphan"
    )
    events: Mapped[list["InterviewEvent"]] = relationship(back_populates="interview")
    transcripts: Mapped[list["Transcript"]] = relationship(back_populates="interview")
    report: Mapped["Report | None"] = relationship(back_populates="interview", uselist=False)
    recordings: Mapped[list["RecordingMetadata"]] = relationship(back_populates="interview")
    code_snapshots: Mapped[list["CodeSnapshot"]] = relationship(back_populates="interview")
    code_operations: Mapped[list["CodeOperation"]] = relationship(back_populates="interview")
    editor_events: Mapped[list["EditorEvent"]] = relationship(back_populates="interview")


class Competency(Base):
    __tablename__ = "competencies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    skill: Mapped[str] = mapped_column(String(128), nullable=False)
    level: Mapped[str] = mapped_column(String(64), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=10)
    source: Mapped[str] = mapped_column(String(32), default="inferred")
    coverage_score: Mapped[float] = mapped_column(Float, default=0.0)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)

    interview: Mapped["Interview"] = relationship(back_populates="competencies")


class InterviewEvent(Base):
    __tablename__ = "interview_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    offset_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="events")


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    speaker: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    offset_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="transcripts")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), unique=True)
    competency_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    weaknesses: Mapped[list] = mapped_column(JSON, default=list)
    communication_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    code_quality_assessment: Mapped[dict] = mapped_column(JSON, default=dict)
    honesty_signals: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence_level: Mapped[float] = mapped_column(Float, default=0.0)
    recommendation: Mapped[str] = mapped_column(String(32))
    final_summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="report")


class RecordingMetadata(Base):
    __tablename__ = "recordings_metadata"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    stream_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="recordings")


class CodeSnapshot(Base):
    __tablename__ = "code_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(32))
    trigger: Mapped[str] = mapped_column(String(64))
    offset_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="code_snapshots")


class CodeOperation(Base):
    __tablename__ = "code_operations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    range_data: Mapped[dict] = mapped_column(JSON, default=dict)
    text_before: Mapped[str | None] = mapped_column(Text)
    text_after: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    interview: Mapped["Interview"] = relationship(back_populates="code_operations")


class EditorEvent(Base):
    __tablename__ = "editor_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    interview_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("interviews.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    lines: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    interview: Mapped["Interview"] = relationship(back_populates="editor_events")
