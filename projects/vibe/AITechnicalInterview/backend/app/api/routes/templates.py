from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import require_admin
from app.database import get_db
from app.schemas.common import CompetencyItem
from app.schemas.template import TemplateCreate, TemplateResponse, TemplateSettingsInput
from app.services.template_manager import TemplateManager

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(require_admin)],
)
manager = TemplateManager()


async def _to_response(db: AsyncSession, t) -> TemplateResponse:
    await db.refresh(t)
    await db.refresh(t, attribute_names=["competencies", "allowed_formats", "settings"])
    return TemplateResponse(
        id=t.id,
        employer_id=t.employer_id,
        name=t.name,
        duration_minutes=t.duration_minutes,
        format_selection_mode=t.format_selection_mode,
        competencies=[
            CompetencyItem(skill=c.skill, level=c.level, weight=c.weight, source=c.source)
            for c in list(t.competencies)
        ],
        allowed_formats=[f.format_name for f in list(t.allowed_formats)],
        settings=TemplateSettingsInput(
            ai_behavior=t.settings.ai_behavior if t.settings else {},
            scoring_rules=t.settings.scoring_rules if t.settings else {},
            evaluation_priorities=t.settings.evaluation_priorities if t.settings else [],
            interview_mode_settings=t.settings.interview_mode_settings if t.settings else {},
        ),
        created_at=t.created_at,
    )


@router.post("", response_model=TemplateResponse)
async def create_template(data: TemplateCreate, db: AsyncSession = Depends(get_db)):
    template = await manager.create(db, data)
    loaded = await manager.get(db, template.id)
    if not loaded:
        raise HTTPException(500, "Template create failed")
    return await _to_response(db, loaded)


@router.get("", response_model=list[TemplateResponse])
async def list_templates(employer_id: UUID, db: AsyncSession = Depends(get_db)):
    templates = await manager.list_by_employer(db, employer_id)
    return [await _to_response(db, t) for t in templates]


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: UUID, db: AsyncSession = Depends(get_db)):
    template = await manager.get(db, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return await _to_response(db, template)
