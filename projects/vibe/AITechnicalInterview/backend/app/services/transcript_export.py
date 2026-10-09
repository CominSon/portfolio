from __future__ import annotations

from datetime import datetime


def format_transcript_txt(history: list[dict]) -> str:
    """
    Читабельная стенограмма для отправки/скачивания.

    history элементы: {speaker, text, offset_ms?, created_at?}
    """
    lines: list[str] = []
    lines.append("СТЕНОГРАММА ИНТЕРВЬЮ")
    lines.append("=" * 80)
    lines.append("")

    def ts(created_at: str | None) -> str:
        if not created_at:
            return ""
        try:
            # ISO from DB, already in UTC; leave as-is for reproducibility.
            dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return created_at

    speaker_ru = {"ai": "AI", "candidate": "Кандидат", "system": "Система"}

    for h in history:
        sp = str(h.get("speaker") or "").strip() or "unknown"
        who = speaker_ru.get(sp, sp)
        created = ts(h.get("created_at"))
        header = f"[{created}] {who}" if created else who
        text = (h.get("text") or "").rstrip()
        lines.append(header)
        lines.append("-" * len(header))
        if text:
            lines.append(text)
        else:
            lines.append("(пусто)")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

