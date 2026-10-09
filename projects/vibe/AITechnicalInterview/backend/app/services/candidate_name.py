"""Быстрое извлечение ФИО из текста резюме / имени файла (без LLM)."""
from __future__ import annotations

import re

_STOP_MARKERS = (
    " мужчина",
    " женщина",
    " +7",
    " 8(",
    " тел",
    " email",
    " e-mail",
    " опыт ",
    " образование",
    " гражданство",
    " дата рождения",
    " желаемая должность",
)

_FIO_RE = re.compile(
    r"^([А-ЯЁA-Z][а-яёa-z]+(?:\s+[А-ЯЁA-Z][а-яёa-z]+){1,3})\b"
)

_GLUED_FILE_RE = re.compile(
    r"^([А-ЯЁA-Z][а-яёa-z]+)([А-ЯЁA-Z]{1,4})$"
)


def humanize_resume_filename(file_name: str | None) -> str | None:
    if not file_name:
        return None
    base = re.sub(r"\.(pdf|docx?|txt)$", "", file_name.strip(), flags=re.I)
    base = re.sub(r"[_-]+", " ", base).strip()
    if not base:
        return None
    m = _GLUED_FILE_RE.match(base)
    if m:
        initials = ".".join(m.group(2)) + "."
        return f"{m.group(1)} {initials}"
    return base


_TITLE_WORDS = {
    "аналитик",
    "разработчик",
    "инженер",
    "программист",
    "менеджер",
    "специалист",
    "консультант",
    "руководитель",
    "директор",
    "студент",
    "data",
    "python",
    "sql",
}


def _strip_trailing_titles(name: str) -> str:
    parts = name.split()
    while len(parts) > 2 and parts[-1].lower().strip(".,") in _TITLE_WORDS:
        parts.pop()
    return " ".join(parts)


def guess_name_from_resume_text(text: str | None) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None
    # Берём начало (у PDF часто всё в одной длинной строке)
    head = re.sub(r"\s+", " ", raw[:300]).strip()
    lower = head.lower()
    cut = len(head)
    for marker in _STOP_MARKERS:
        idx = lower.find(marker)
        if idx > 5:
            cut = min(cut, idx)
    head = head[:cut].strip(" ,.—–-;")
    m = _FIO_RE.match(head)
    if m:
        return _strip_trailing_titles(m.group(1))[:255]
    # 2–4 слова с заглавной
    parts = head.split()
    words: list[str] = []
    for p in parts[:4]:
        if re.match(r"^[А-ЯЁA-Z][а-яёa-z]+$", p):
            if p.lower() in _TITLE_WORDS:
                break
            words.append(p)
        else:
            break
    if len(words) >= 2:
        return " ".join(words)[:255]
    return None


def resolve_candidate_name(
    *,
    manual_name: str | None = None,
    resume_text: str | None = None,
    resume_filename: str | None = None,
) -> str | None:
    manual = (manual_name or "").strip() or None
    if manual and not re.search(r"\.(pdf|docx?)$", manual, re.I):
        return manual[:255]
    from_text = guess_name_from_resume_text(resume_text)
    if from_text:
        return from_text
    return humanize_resume_filename(resume_filename)
