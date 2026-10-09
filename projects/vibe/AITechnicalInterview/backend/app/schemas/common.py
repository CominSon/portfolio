from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CompetencyItem(BaseModel):
    skill: str
    level: str
    weight: int = Field(ge=1, le=100)
    source: str = "inferred"


class EmployerCreate(BaseModel):
    name: str
    email: EmailStr
    contact_emails: list[EmailStr] = Field(default_factory=list)


class EmployerContactEmailsUpdate(BaseModel):
    emails: list[EmailStr] = Field(default_factory=list)


class EmployerResponse(BaseModel):
    id: UUID
    name: str
    email: str
    contact_emails: list[str] = Field(default_factory=list)
    created_at: datetime

    model_config = {"from_attributes": True}
