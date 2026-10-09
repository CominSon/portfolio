"""Очистка мусора из STT (типичные фантомные «субтитры» Whisper)."""
import re

_JUNK_LINE_PATTERNS = (
    re.compile(r"субтитр", re.I),
    re.compile(r"subtitles?", re.I),
    re.compile(r"корректор\s", re.I),
    re.compile(r"редактор\s+субтитр", re.I),
    re.compile(r"а\.синецкая|а\.егорова", re.I),
    re.compile(r"^\s*продолжение\s+следует", re.I),
    re.compile(r"^\s*спасибо\s+за\s+внимание", re.I),
    re.compile(r"^\s*до\s+свидания\s*$", re.I),
    re.compile(r"^\s*музык", re.I),
)

_JUNK_PHRASES = (
    "субтитры субтитров",
    "редактор субтитров",
    "корректор а.",
    "продолжение следует",
)


def _line_is_junk(line: str) -> bool:
    t = line.strip()
    if not t or len(t) < 3:
        return True
    low = t.lower()
    if any(p in low for p in _JUNK_PHRASES):
        return True
    return any(p.search(t) for p in _JUNK_LINE_PATTERNS)


def sanitize_stt_text(text: str) -> str:
    if not (text or "").strip():
        return ""
    lines = re.split(r"[\n\r]+|(?<=[.!?…])\s+", text.strip())
    kept: list[str] = []
    for line in lines:
        part = line.strip()
        if not part or _line_is_junk(part):
            continue
        kept.append(part)
    if not kept:
        return ""
    merged = " ".join(kept)
    merged = re.sub(r"\s{2,}", " ", merged).strip()
    return merged
