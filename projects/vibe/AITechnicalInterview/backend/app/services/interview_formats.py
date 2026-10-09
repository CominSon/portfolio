"""Подсказки для промпта по каждому формату интервью."""

LEGACY_AI_ASSISTED_FORMAT = "AI-Assisted Interview"

FORMAT_GUIDANCE: dict[str, str] = {
    "Live Coding": (
        "Live Coding: давайте задачи в редакторе, оценивайте ход решения и финальный код. "
        "Короткие устные комментарии кандидата + правки в редакторе. "
        "Типичная сложность: одна функция, небольшой модуль, точечная правка. "
        "Для SQL: в стартовом сниппете дайте схему + несколько строк sample-данных."
    ),
    "Code Review": (
        "Code Review: разбор готового кода в редакторе — ошибки, стиль, риски, производительность. "
        "Каждая новая задача: полный сниппет в code_actions (action replace). "
        "Для SQL: в сниппете обязательно схема таблицы + 3–6 строк sample-данных (INSERT или комментарий-таблица), "
        "затем сам запрос/задание — без «голой» формулировки без данных. "
        "ЗАПРЕЩЕНЫ общие поведенческие вопросы («кейс из практики», «почему выбрали подход») без кода. "
        "Не просите писать проект с нуля — только ревью и точечные правки."
    ),
    "Architecture Interview": (
        "Architecture Interview: проектирование систем, компоненты, масштаб, компромиссы, "
        "надёжность. Код в редакторе опционален (схемы/псевдокод в message допустимы текстом)."
    ),
}

LIVE_CODING_AI_ASSISTANT_GUIDANCE = (
    "Live Coding с AI-помощником (кандидат пишет код в редакторе, как с Copilot/Cursor): "
    "задачи ЗНАЧИТЕЛЬНО сложнее обычного live coding — цельная ситуация/продуктовая задача, "
    "решение на несколько модулей/классов/файлов, а не «напишите одну функцию». "
    "Оценивай: как кандидат декомпозирует задачу, формулирует запросы к AI-помощнику, "
    "проверяет и дорабатывает сгенерированный код, оставляет пояснения в коде (комментарии). "
    "Не требуй буквального копирования промптов в ответ — смотри на итоговый код и устные рассуждения. "
    "В code_actions можно дать стартовый каркас (скелет проекта), но основную работу кандидат делает сам."
)

ALL_FORMATS = list(FORMAT_GUIDANCE.keys())


def normalize_format_list(formats: list[str] | None) -> list[str]:
    """Убрать устаревший отдельный формат AI-Assisted."""
    if not formats:
        return []
    return [f for f in formats if f and f.strip() != LEGACY_AI_ASSISTED_FORMAT]


def is_live_coding_format(format_name: str | None) -> bool:
    return "Live Coding" in (format_name or "")


def get_live_coding_ai_assistant(interview) -> bool:
    settings = interview.ai_settings if isinstance(interview.ai_settings, dict) else {}
    if settings.get("live_coding_ai_assistant"):
        return True
    fmt = interview.selected_format or ""
    return LEGACY_AI_ASSISTED_FORMAT in fmt


def set_live_coding_ai_assistant(interview, enabled: bool) -> None:
    settings = dict(interview.ai_settings or {})
    settings["live_coding_ai_assistant"] = bool(enabled)
    interview.ai_settings = settings


SESSION_MODE_TEST = "test"
SESSION_MODE_FULL = "full"
DEFAULT_TEST_MAX_TURNS = 2
DEFAULT_FULL_DURATION_MINUTES = 60


def get_session_mode(interview) -> str:
    """Режим сессии: test | full. Пусто в ai_settings → из глобального .env."""
    settings = interview.ai_settings if isinstance(interview.ai_settings, dict) else {}
    mode = str(settings.get("session_mode") or "").strip().lower()
    if mode in (SESSION_MODE_TEST, SESSION_MODE_FULL):
        return mode
    from app.config import get_settings

    return SESSION_MODE_TEST if get_settings().interview_test_mode else SESSION_MODE_FULL


def set_session_mode(interview, mode: str, *, test_max_turns: int | None = None) -> None:
    """Сохранить режим прогона и длительность интервью."""
    normalized = str(mode or "").strip().lower()
    if normalized not in (SESSION_MODE_TEST, SESSION_MODE_FULL):
        normalized = SESSION_MODE_FULL
    settings = dict(interview.ai_settings or {})
    settings["session_mode"] = normalized
    if normalized == SESSION_MODE_TEST:
        turns = int(test_max_turns) if test_max_turns and test_max_turns > 0 else DEFAULT_TEST_MAX_TURNS
        settings["test_max_turns"] = turns
        interview.duration_minutes = DEFAULT_FULL_DURATION_MINUTES
    else:
        settings.pop("test_max_turns", None)
        interview.duration_minutes = DEFAULT_FULL_DURATION_MINUTES
    interview.ai_settings = settings


def interview_is_test_mode(interview) -> bool:
    return get_session_mode(interview) == SESSION_MODE_TEST


def interview_test_max_turns(interview) -> int:
    settings = interview.ai_settings if isinstance(interview.ai_settings, dict) else {}
    raw = settings.get("test_max_turns")
    if isinstance(raw, int) and raw > 0:
        return raw
    from app.config import get_settings

    return max(1, int(get_settings().interview_test_max_turns or DEFAULT_TEST_MAX_TURNS))


def format_guidance_block(format_name: str, *, live_coding_ai_assistant: bool = False) -> str:
    name = (format_name or "Live Coding").strip()
    parts = [p.strip() for p in name.split("+") if p.strip()]
    parts = [p for p in parts if p != LEGACY_AI_ASSISTED_FORMAT]
    if not parts:
        parts = ["Live Coding"]
    lines = [
        FORMAT_GUIDANCE.get(p, f"Формат «{p}»: следуйте логике этого типа собеседования.")
        for p in parts
    ]
    if live_coding_ai_assistant and is_live_coding_format(name):
        lines.append(LIVE_CODING_AI_ASSISTANT_GUIDANCE)
    return "Режим интервью:\n" + "\n".join(f"- {line}" for line in lines)
