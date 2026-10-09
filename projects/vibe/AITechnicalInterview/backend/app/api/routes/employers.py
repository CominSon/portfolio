from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException  # noqa: F401 — HTTPException used below
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin_auth import require_admin
from app.api.serialize import employer_to_response
from app.database import get_db
from app.models.entities import Employer
from app.schemas.common import EmployerContactEmailsUpdate, EmployerCreate, EmployerResponse
from app.services.employer_contacts import merge_contact_emails, normalize_email

router = APIRouter(
    prefix="/employers",
    tags=["employers"],
    dependencies=[Depends(require_admin)],
)


@router.post("", response_model=EmployerResponse)
async def create_employer(data: EmployerCreate, db: AsyncSession = Depends(get_db)):
    email = data.email.strip().lower()
    result = await db.execute(select(Employer).where(func.lower(Employer.email) == email))
    employer = result.scalar_one_or_none()
    contacts = merge_contact_emails(email, [str(e) for e in data.contact_emails])
    if employer is None:
        employer = Employer(name=data.name, email=email, contact_emails=contacts)
        db.add(employer)
        await db.flush()
    else:
        employer.name = data.name
        employer.contact_emails = merge_contact_emails(email, list(employer.contact_emails or []) + contacts)
        await db.flush()
    return await employer_to_response(db, employer)


@router.put("/{employer_id}/contact-emails", response_model=EmployerResponse)
async def update_contact_emails(
    employer_id: UUID, data: EmployerContactEmailsUpdate, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(Employer).where(Employer.id == employer_id))
    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(404, "Employer not found")
    employer.contact_emails = merge_contact_emails(employer.email, [str(e) for e in data.emails])
    await db.flush()
    return await employer_to_response(db, employer)


@router.post("/{employer_id}/contact-emails/{email}")
async def remember_contact_email(employer_id: UUID, email: str, db: AsyncSession = Depends(get_db)):
    """Добавить email в историю работодателя (для выпадающего списка в Admin)."""
    result = await db.execute(select(Employer).where(Employer.id == employer_id))
    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(404, "Employer not found")
    normalized = normalize_email(email)
    if not normalized:
        raise HTTPException(400, "Invalid email")
    employer.contact_emails = merge_contact_emails(
        employer.email, list(employer.contact_emails or []) + [normalized]
    )
    await db.flush()
    return {"contact_emails": employer.contact_emails}


@router.get("/{employer_id}", response_model=EmployerResponse)
async def get_employer(employer_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employer).where(Employer.id == employer_id))
    employer = result.scalar_one_or_none()
    if not employer:
        raise HTTPException(404, "Employer not found")
    return await employer_to_response(db, employer)
