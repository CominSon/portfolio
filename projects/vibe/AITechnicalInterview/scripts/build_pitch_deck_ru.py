#!/usr/bin/env python3
"""
Генерация презентации MVP в PPTX.

Запуск:
  backend/.venv/bin/python scripts/build_pitch_deck_ru.py
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "MVP_PITCH_DECK_RU.pptx"


def add_title(prs: Presentation, title: str, subtitle: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle


def add_bullets(prs: Presentation, title: str, bullets: list[str]) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = title
    tf = slide.shapes.placeholders[1].text_frame
    tf.clear()
    for i, b in enumerate(bullets):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = b
        p.level = 0


def add_example(prs: Presentation, title: str, interview_id: str, report_hint: str, video_url: str) -> None:
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title Only
    slide.shapes.title.text = title

    left = Inches(0.8)
    top = Inches(1.7)
    width = Inches(12.0)
    height = Inches(4.8)
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = f"Пример интервью: {interview_id}"
    p.font.size = Pt(20)

    p = tf.add_paragraph()
    p.text = "Итог (фрагмент отчёта):"
    p.font.size = Pt(16)

    p = tf.add_paragraph()
    p.text = report_hint
    p.level = 1
    p.font.size = Pt(14)

    p = tf.add_paragraph()
    p.text = "Видео:"
    p.font.size = Pt(16)

    p = tf.add_paragraph()
    p.text = video_url
    p.level = 1
    p.font.size = Pt(14)


def main() -> None:
    prs = Presentation()

    add_title(
        prs,
        "AI Technical Interview — MVP",
        "Платформа для автоматизации технических интервью: вопросы, код, запись, отчёт, видео.",
    )

    add_bullets(
        prs,
        "Что делает MVP",
        [
            "Создаёт сессию интервью и выдаёт ссылку кандидату",
            "Проводит интервью: вопросы + live coding + голос (TTS/STT)",
            "Записывает экран/камеру/аудио и собирает итоговый MP4",
            "Формирует отчёт: сильные/слабые стороны, рекомендации, риски",
        ],
    )

    add_bullets(
        prs,
        "Технологии (внутри)",
        [
            "Backend: FastAPI + SQLAlchemy (SQLite/PostgreSQL)",
            "Frontend: React + Vite + Monaco Editor",
            "STT: faster-whisper (локально)",
            "TTS: Silero (офлайн) / Edge TTS (опционально)",
            "Видео: MediaRecorder (webm) + ffmpeg montage (mp4)",
        ],
    )

    add_bullets(
        prs,
        "Польза для работодателя (Штаб УБ / Штаб B2C)",
        [
            "Сокращение времени инженеров на первичные техсобесы",
            "Быстрый отсев слабых кандидатов на ранней стадии",
            "Единый формат отчётов и сравнимость кандидатов",
            "Увеличение пропускной способности: больше кандидатов → выше шанс найти сильного",
        ],
    )

    add_bullets(
        prs,
        "Польза для кандидата",
        [
            "Меньше стресса: нет «экзамена с человеком», можно думать и писать спокойно",
            "Ближе к реальной работе: объяснения, план, итеративное решение",
            "Выше шанс показать реальные знания, а не провалиться из-за волнения",
            "Лучше подходит «тихим» кандидатам и тем, кто хуже проходит классический live coding",
        ],
    )

    add_bullets(
        prs,
        "Что улучшить дальше (следующий этап)",
        [
            "Учитывать резюме/опыт при вопросах (персонализация)",
            "Стенограмма всей сессии + авто-правка ошибок (LLM постобработка)",
            "Стабильный домен без зависимости от quick tunnel",
            "Аналитика: метрики по вопросам, времени, качеству ответов",
        ],
    )

    # Пример по последнему интервью из базы — подставляем «живую» ссылку как шаблон
    add_example(
        prs,
        "Пример результата (из быстрого интервью)",
        interview_id="366d3333-5d96-44b3-b264-09beba8d1b9a",
        report_hint="Коммуникация адекватная; кандидат ясно излагает мысли. (Важно: учитываем и рассуждения во время кодинга.)",
        video_url="(ссылка зависит от текущего trycloudflare URL, добавьте её из письма/админки)",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    print(f"OK: {OUT}")


if __name__ == "__main__":
    main()

