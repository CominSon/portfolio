"""Постобработка отчёта: не штрафовать кандидата за STT и сбои интервьюера."""
import re
from typing import Any

_AGENT_GENERIC_PHRASE = "перейдём к следующему аспекту"

# Не включать в weaknesses / не критиковать в communication
_WEAKNESS_DROP_RE = re.compile(
    r"опечатк|"
    r"love\s*join|"
    r"переспрашива|"
    r"невнимателен\s+к\s+формулировк|"
    r"требовалось\s+уточнение\s+вопроса|"
    r"требует\s+уточнени",
    re.I,
)

_ADDITIONAL_INTERVIEW_RE = re.compile(
    r"дополнительн\w*\s+(технич\w*\s+)?интервью|"
    r"повторн\w*\s+интервью|"
    r"ещё\s+одно\s+интервью|"
    r"провести\s+ещё\s+одн",
    re.I,
)

_COMM_FIX_DROP_RE = re.compile(
    r"требовалось\s+уточнение|переспрашива|невнимателен\s+к\s+формулировк",
    re.I,
)


def agent_issues_from_transcript(transcript_history: list[dict]) -> str:
    """Контекст для LLM: сбои интервьюера и STT."""
    generic_count = 0
    candidate_complaints = 0
    for h in transcript_history:
        text = (h.get("text") or "").lower()
        speaker = h.get("speaker", "")
        if speaker == "ai" and _AGENT_GENERIC_PHRASE in text:
            generic_count += 1
        if speaker == "candidate" and any(
            p in text
            for p in (
                "какой аспект",
                "не вижу изменений",
                "не дал никаких новых",
                "опять не дал",
                "нет новых задач",
            )
        ):
            candidate_complaints += 1

    lines = [
        "Контекст оценки (обязательно учесть):",
        "- Устная речь кандидата в стенограмме — автоматическая транскрипция (STT). "
        "Искажения терминов (например «Love Join» вместо LEFT JOIN) — артефакт STT, "
        "НЕ опечатки и НЕ слабость кандидата. Не упоминать в weaknesses.",
        "- Оценивать только технические навыки, код в редакторе и содержательные устные объяснения.",
        "- Не включать в weaknesses: «переспрашивает», «невнимателен к формулировкам», "
        "«требуется уточнение вопроса» — если это реакция на неконкретные ответы интервьюера.",
    ]
    if generic_count:
        lines.append(
            f"- Интервьюер {generic_count} раз(а) отвечал шаблоном «перейдём к следующему аспекту» "
            "без новой задачи — переспросы кандидата в этих эпизодах не считать минусом."
        )
    if candidate_complaints:
        lines.append(
            f"- Кандидат {candidate_complaints} раз(а) указывал, что не видит новой задачи/изменений в редакторе — "
            "это проблема ведения интервью, не коммуникации кандидата."
        )
    return "\n".join(lines)


def sanitize_report_data(data: dict[str, Any]) -> dict[str, Any]:
    """Убрать из отчёта пункты, основанные на STT и сбоях агента."""
    out = dict(data)

    weaknesses = [
        w
        for w in (out.get("weaknesses") or [])
        if isinstance(w, str)
        and w.strip()
        and not _WEAKNESS_DROP_RE.search(w)
        and not _ADDITIONAL_INTERVIEW_RE.search(w)
    ]
    out["weaknesses"] = weaknesses

    comm = dict(out.get("communication_assessment") or {})
    for key in list(comm.keys()):
        val = str(comm.get(key, ""))
        if _COMM_FIX_DROP_RE.search(val):
            if key == "итог":
                comm[key] = (
                    "Кандидат объясняет решения по существу; отдельные уточнения связаны "
                    "с формулировками интервьюера, а не с нежеланием отвечать."
                )
            elif key in ("ясность", "вовлечённость"):
                comm[key] = val
                for bad in ("требовалось уточнение", "переспрашива", "невнимателен"):
                    if bad in val.lower():
                        comm[key] = (
                            "Достаточно ясно по технике; уточнял вопрос при неясных репликах интервьюера."
                        )
                        break
    out["communication_assessment"] = comm

    summary = str(out.get("final_summary") or "")
    if _ADDITIONAL_INTERVIEW_RE.search(summary):
        summary = _ADDITIONAL_INTERVIEW_RE.sub("", summary)
        summary = re.sub(r"\s{2,}", " ", summary).strip(" ,.;")
    if _WEAKNESS_DROP_RE.search(summary):
        summary = re.sub(
            r"[^.]*(?:опечатк|переспрашива|невнимателен к формулировк)[^.]*\.?\s*",
            "",
            summary,
            flags=re.I,
        )
        out["final_summary"] = summary.strip() or out.get("final_summary", "")
    else:
        out["final_summary"] = summary

    return out
