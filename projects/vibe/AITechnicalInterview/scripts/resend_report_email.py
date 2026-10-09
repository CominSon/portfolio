#!/usr/bin/env python3
"""Повторная отправка итогового письма (отчёт + видео + стенограмма)."""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import async_session_factory
from app.models.entities import Interview
from app.services.email_notify import send_report_email, send_video_email
from app.services.interview_montage_service import build_interview_montage, montage_is_ready


async def main(
    interview_id: str | None,
    to_email: str,
    *,
    report_only: bool = False,
    video_only: bool = False,
    skip_rebuild: bool = False,
) -> None:
    async with async_session_factory() as db:
        if interview_id:
            uid = (
                UUID(interview_id.replace("-", ""))
                if len(interview_id) == 32
                else UUID(interview_id)
            )
            q = select(Interview).where(Interview.id == uid)
        else:
            q = (
                select(Interview)
                .where(Interview.status.in_(("report_ready", "completed", "completing")))
                .order_by(Interview.ended_at.desc().nullslast(), Interview.created_at.desc())
                .limit(1)
            )

        result = await db.execute(
            q.options(selectinload(Interview.report), selectinload(Interview.candidate))
        )
        interview = result.scalar_one_or_none()
        if not interview:
            print("Интервью не найдено")
            sys.exit(1)
        print(f"Интервью: {interview.id}  status={interview.status}  ended={interview.ended_at}")
        if not interview.report and not video_only:
            print("Отчёт ещё не сформирован — сначала scripts/regenerate_report.py")
            sys.exit(1)

        from app.services.datetime_utils import format_moscow
        from app.services.resume_analyzer import candidate_display_name

        interview_meta = {
            "candidate_name": candidate_display_name(interview),
            "format": interview.selected_format,
            "editor_language": interview.editor_language,
            "started_at": format_moscow(interview.started_at),
            "ended_at": format_moscow(interview.ended_at),
        }

        rebuild_montage = not skip_rebuild and not report_only
        if video_only or rebuild_montage:
            if not montage_is_ready(interview.id) or rebuild_montage:
                print("Сборка итогового видео (обычно 3–10 минут для ~7 мин интервью)…")
                print("  Не закрывайте терминал. Прогресс — строки «… N%» ниже.")
                montage = await build_interview_montage(
                    db, interview.id, force_rebuild=rebuild_montage
                )
                if not montage and (video_only or (not report_only and rebuild_montage)):
                    print("Ошибка: видео не собрано.")
                    sys.exit(1)
                if montage:
                    print(f"Видео: {montage}")
            elif montage_is_ready(interview.id):
                print("Видео уже есть, пересборка пропущена (--skip-rebuild).")

        if report_only and interview.report:
            pending = not montage_is_ready(interview.id)
            print("Отправка только отчёта…")
            report = interview.report
            data = {
                "competency_scores": report.competency_scores or {},
                "strengths": report.strengths or [],
                "weaknesses": report.weaknesses or [],
                "communication_assessment": report.communication_assessment or {},
                "code_quality_assessment": report.code_quality_assessment or {},
                "honesty_signals": report.honesty_signals or {},
                "confidence_level": report.confidence_level,
                "recommendation": report.recommendation,
                "final_summary": report.final_summary or "",
            }
            ok = send_report_email(
                [to_email],
                f"Отчёт AI-интервью {interview.id}",
                "",
                report_data=data,
                interview_meta=interview_meta,
                interview_id=interview.id,
                video_pending=pending,
            )
            if not ok:
                print("Не удалось отправить отчёт — см. лог backend / пароль приложения Mail.ru")
                sys.exit(1)
            print(f"Отчёт отправлен на {to_email}")

        if not report_only:
            print("Отправка единого письма (итоги + видео + стенограмма)…")
            report_data = None
            if interview.report:
                report_data = {
                    "competency_scores": interview.report.competency_scores or {},
                    "strengths": interview.report.strengths or [],
                    "weaknesses": interview.report.weaknesses or [],
                    "communication_assessment": interview.report.communication_assessment or {},
                    "code_quality_assessment": interview.report.code_quality_assessment or {},
                    "honesty_signals": interview.report.honesty_signals or {},
                    "confidence_level": interview.report.confidence_level,
                    "recommendation": interview.report.recommendation,
                    "final_summary": interview.report.final_summary or "",
                }
            ok = send_video_email([to_email], interview.id, interview_meta, report_data=report_data)
            if ok:
                print(f"Единое письмо отправлено на {to_email} (интервью {interview.id})")
            else:
                print("Не удалось отправить единое письмо — см. лог backend")
                sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Использование: python scripts/resend_report_email.py EMAIL [interview_id] [опции]\n"
            "  interview_id опционален — по умолчанию последнее завершённое\n"
            "  --report-only   только отчёт (без видео/стенограммы)\n"
            "  --video-only    только единое письмо (без отдельного письма отчёта)\n"
            "  --skip-rebuild  не пересобирать montage, если файл уже есть"
        )
        sys.exit(1)
    args = [a for a in sys.argv[1:] if a.startswith("--")]
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    email = positional[0].strip()
    iid = positional[1].strip() if len(positional) > 1 else None
    asyncio.run(
        main(
            iid,
            email,
            report_only="--report-only" in args,
            video_only="--video-only" in args,
            skip_rebuild="--skip-rebuild" in args,
        )
    )
