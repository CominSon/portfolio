"""Человекочитаемый отчёт на русском для работодателя."""
from typing import Any

RECOMMENDATION_RU = {
    "reject": "Не рекомендован",
    "weak_fit": "Слабое соответствие",
    "good_fit": "Подходит на роль",
    "strong_fit": "Сильно рекомендован",
}


def format_report_text_ru(data: dict[str, Any], interview_meta: dict[str, Any] | None = None) -> str:
    meta = interview_meta or {}
    rec = data.get("recommendation", "weak_fit")
    rec_label = RECOMMENDATION_RU.get(rec, rec)

    lines = [
        "ОТЧЁТ ПО ТЕХНИЧЕСКОМУ ИНТЕРВЬЮ",
        "=" * 60,
    ]
    if meta.get("candidate_name"):
        lines.append(f"Кандидат: {meta['candidate_name']}")
    if meta.get("format"):
        lines.append(f"Формат: {meta['format']}")
    if meta.get("editor_language"):
        lines.append(f"Язык в редакторе: {meta['editor_language']}")
    if meta.get("started_at"):
        lines.append(f"Начало: {meta['started_at']}")
    if meta.get("ended_at"):
        lines.append(f"Окончание: {meta['ended_at']}")

    lines.extend(
        [
            "",
            f"ИТОГОВАЯ РЕКОМЕНДАЦИЯ: {rec_label} ({rec})",
            f"Уверенность оценки: {int(float(data.get('confidence_level', 0)) * 100)}%",
            "",
            "—" * 60,
            "КРАТКОЕ ЗАКЛЮЧЕНИЕ",
            "—" * 60,
            (data.get("final_summary") or "Нет данных.").strip(),
        ]
    )

    scores = data.get("competency_scores") or {}
    if scores:
        lines.extend(["", "—" * 60, "ОЦЕНКИ ПО КОМПЕТЕНЦИЯМ (0–100)", "—" * 60])
        for skill, score in scores.items():
            lines.append(f"  • {skill}: {score}/100")

    quiz_acc = data.get("warmup_quiz_accuracy")
    if quiz_acc is not None:
        weight_pct = int(float(data.get("warmup_quiz_weight", 0.15)) * 100)
        offered = data.get("warmup_quiz_offered", 0)
        correct = data.get("warmup_quiz_correct", 0)
        lines.extend(
            [
                "",
                "—" * 60,
                f"МИНИ-ТЕСТ ВО ВРЕМЯ ПАУЗ (озвучка готовится, вес ~{weight_pct}%)",
                "—" * 60,
                (
                    f"  • Пока обрабатывались ответы, кандидату предлагали короткие проверочные "
                    f"вопросы: {offered} шт., верных ответов {correct} ({quiz_acc}%). "
                    f"Это вспомогательная проверка, не основная часть собеседования."
                ),
            ]
        )

    strengths = data.get("strengths") or []
    if strengths:
        lines.extend(["", "СИЛЬНЫЕ СТОРОНЫ:"])
        for s in strengths:
            lines.append(f"  + {s}")

    weaknesses = data.get("weaknesses") or []
    if weaknesses:
        lines.extend(["", "ЗОНЫ РОСТА / РИСКИ:"])
        for w in weaknesses:
            lines.append(f"  − {w}")

    comm = data.get("communication_assessment")
    if comm:
        lines.extend(["", "КОММУНИКАЦИЯ:"])
        if isinstance(comm, dict):
            for k, v in comm.items():
                lines.append(f"  • {k}: {v}")
        else:
            lines.append(f"  {comm}")

    code_q = data.get("code_quality_assessment")
    if code_q:
        lines.extend(["", "КАЧЕСТВО КОДА:"])
        if isinstance(code_q, dict):
            for k, v in code_q.items():
                lines.append(f"  • {k}: {v}")
        else:
            lines.append(f"  {code_q}")

    honesty = data.get("honesty_signals")
    if honesty:
        lines.extend(["", "ЧЕСТНОСТЬ / РАБОТА С НЕЗНАНИЕМ:"])
        if isinstance(honesty, dict):
            for k, v in honesty.items():
                lines.append(f"  • {k}: {v}")
        else:
            lines.append(f"  {honesty}")

    return "\n".join(lines)
