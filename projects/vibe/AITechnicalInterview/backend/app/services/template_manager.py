import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import (
    Interview,
    InterviewTemplate,
    TemplateAllowedFormat,
    TemplateCompetency,
    TemplateSettings,
)
from app.schemas.template import TemplateCreate


class TemplateManager:
    async def create(self, db: AsyncSession, data: TemplateCreate) -> InterviewTemplate:
        template = InterviewTemplate(
            employer_id=data.employer_id,
            name=data.name,
            duration_minutes=data.duration_minutes,
            job_description_text=data.job_description_text,
            format_selection_mode=data.format_selection_mode,
        )
        db.add(template)
        await db.flush()

        for c in data.competencies:
            db.add(
                TemplateCompetency(
                    template_id=template.id,
                    skill=c.skill,
                    level=c.level,
                    weight=c.weight,
                    source=c.source,
                )
            )
        for fmt in data.allowed_formats:
            db.add(TemplateAllowedFormat(template_id=template.id, format_name=fmt))
        db.add(
            TemplateSettings(
                template_id=template.id,
                ai_behavior=data.settings.ai_behavior,
                scoring_rules=data.settings.scoring_rules,
                evaluation_priorities=data.settings.evaluation_priorities,
                interview_mode_settings=data.settings.interview_mode_settings,
            )
        )
        await db.flush()
        return template

    async def get(self, db: AsyncSession, template_id: uuid.UUID) -> InterviewTemplate | None:
        result = await db.execute(
            select(InterviewTemplate)
            .where(InterviewTemplate.id == template_id)
            .options(
                selectinload(InterviewTemplate.competencies),
                selectinload(InterviewTemplate.allowed_formats),
                selectinload(InterviewTemplate.settings),
            )
        )
        return result.scalar_one_or_none()

    async def list_by_employer(self, db: AsyncSession, employer_id: uuid.UUID) -> list[InterviewTemplate]:
        result = await db.execute(
            select(InterviewTemplate)
            .where(InterviewTemplate.employer_id == employer_id)
            .options(
                selectinload(InterviewTemplate.competencies),
                selectinload(InterviewTemplate.allowed_formats),
                selectinload(InterviewTemplate.settings),
            )
        )
        return list(result.scalars().all())

    async def apply_to_interview(self, db: AsyncSession, interview: Interview, template: InterviewTemplate) -> None:
        interview.duration_minutes = template.duration_minutes
        interview.job_description_text = template.job_description_text
        interview.format_selection_mode = template.format_selection_mode
        interview.allowed_formats = [f.format_name for f in template.allowed_formats]
        if template.settings:
            interview.ai_settings = {
                "ai_behavior": template.settings.ai_behavior,
                "scoring_rules": template.settings.scoring_rules,
                "evaluation_priorities": template.settings.evaluation_priorities,
                "interview_mode_settings": template.settings.interview_mode_settings,
            }
