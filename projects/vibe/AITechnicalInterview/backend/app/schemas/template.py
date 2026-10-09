from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import CompetencyItem


class TemplateSettingsInput(BaseModel):
    ai_behavior: dict = Field(default_factory=dict)
    scoring_rules: dict = Field(default_factory=dict)
    evaluation_priorities: list[str] = Field(default_factory=list)
    interview_mode_settings: dict = Field(default_factory=dict)


class TemplateCreate(BaseModel):
    employer_id: UUID
    name: str
    duration_minutes: int = 60
    job_description_text: str | None = None
    competencies: list[CompetencyItem] = Field(default_factory=list)
    allowed_formats: list[str] = Field(default_factory=list)
    format_selection_mode: str = "auto"
    settings: TemplateSettingsInput = Field(default_factory=TemplateSettingsInput)


class TemplateResponse(BaseModel):
    id: UUID
    employer_id: UUID
    name: str
    duration_minutes: int
    format_selection_mode: str
    competencies: list[CompetencyItem]
    allowed_formats: list[str]
    settings: TemplateSettingsInput
    created_at: datetime

    model_config = {"from_attributes": True}
