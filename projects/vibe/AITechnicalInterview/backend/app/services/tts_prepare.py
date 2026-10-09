"""Подготовка текста для Silero: род говорящего, паузы, разбивка на фразы."""
import re

FEMALE_VOICES = frozenset({
    "baya", "kseniya", "xenia",
    "alena", "jane", "omazh", "oksana", "dasha", "masha", "marina", "julia",
    "alena:premium",
})
MALE_VOICES = frozenset({
    "aidar", "eugene",
    "filipp", "zahar", "ermil", "alexander", "kirill", "anton", "filipp:premium",
})

# Silero ru плохо читает латиницу — заменяем на русскую фонетику
_TECH_TTS_RU: tuple[tuple[str, str], ...] = (
    ("JavaScript", "Джаваскрипт"),
    ("TypeScript", "Тайпскрипт"),
    ("PostgreSQL", "Постгрес"),
    ("Kubernetes", "Кубернетис"),
    ("GitHub", "Гитхаб"),
    ("GitLab", "Гитлаб"),
    ("Node.js", "Нод джей эс"),
    ("React", "Реакт"),
    ("Docker", "Докер"),
    ("Redis", "Редис"),
    ("MongoDB", "Монго диби"),
    ("GraphQL", "ГрафКуЭль"),
    ("FastAPI", "Фаст Эй Пи Ай"),
    ("DeepSeek", "ДипСик"),
    ("Python", "Пайтон"),
    ("Golang", "Го"),
    ("Kotlin", "Котлин"),
    ("Swift", "Свифт"),
    ("Scala", "Скала"),
    ("Rust", "Раст"),
    ("Java", "Джава"),
    ("Linux", "Линукс"),
    ("Nginx", "Энжинекс"),
    ("HTTP", "эйч-ти-ти-пи"),
    ("HTTPS", "эйч-ти-ти-пи-эс"),
    ("API", "эй-пи-ай"),
    ("SQL", "эс-кью-эль"),
    ("JSON", "джейсон"),
    ("YAML", "ямл"),
    ("HTML", "эйч-ти-эм-эль"),
    ("CSS", "цэ-эс-эс"),
    ("ORM", "о-эр-эм"),
    ("CI/CD", "си-ай си-ди"),
    ("Go", "Го"),
)


def is_female_voice(speaker: str) -> bool:
    s = speaker.lower()
    if s in FEMALE_VOICES:
        return True
    if s in MALE_VOICES:
        return False
    return True


def briefing_text(speaker: str) -> str:
    if is_female_voice(speaker):
        return (
            "Здравствуйте! Меня зовут Айри, я — ваш AI-интервьюер. "
            "Я готова провести техническое интервью. "
            "Обязательно включите камеру, микрофон и демонстрацию всего экрана — без этого интервью не начнётся. "
            "Когда всё подключено, нажмите «Начать интервью»."
        )
    return (
        "Здравствуйте! Меня зовут Айри, я — ваш AI-интервьюер. "
        "Я готов провести техническое интервью. "
        "Обязательно включите камеру, микрофон и демонстрацию всего экрана — без этого интервью не начнётся. "
        "Когда всё подключено, нажмите «Начать интервью»."
    )


_ANSWER_HINT = (
    " Говорите свободно — микрофон записывает всё время. "
    "Когда закончите ответ, нажмите «Ответить»."
)


def opening_turn_text(
    speaker: str,
    skills: list[str],
    *,
    resume_profile: dict | None = None,
) -> str:
    """
    Первая реплика интервьюера.
    Если есть resume_profile от LLM — используем opening_question (без зачитывания резюме).
    """
    if resume_profile:
        q = str(resume_profile.get("opening_question") or "").strip()
        if q:
            if "Ответить" not in q:
                q += _ANSWER_HINT
            return q

    focus = ", ".join(skills[:3]) if skills else "заявленным в вакансии навыкам"
    if is_female_voice(speaker):
        return (
            f"Отлично, начинаем. Я готова задавать вопросы по {focus}. "
            "Для начала расскажите о вашем последнем техническом проекте: "
            "роль, стек и главный результат."
            f"{_ANSWER_HINT}"
        )
    return (
        f"Отлично, начинаем. Я готов задавать вопросы по {focus}. "
        "Для начала расскажите о вашем последнем техническом проекте: "
        "роль, стек и главный результат."
        f"{_ANSWER_HINT}"
    )


def localize_tech_terms_for_tts(text: str) -> str:
    """Латинские IT-термины → русская фонетика для Silero."""
    t = text
    for en, ru in sorted(_TECH_TTS_RU, key=lambda p: -len(p[0])):
        t = re.sub(rf"(?<![\w-]){re.escape(en)}(?![\w-])", ru, t, flags=re.IGNORECASE)
    return t


def prepare_for_tts(text: str, speaker: str) -> str:
    """Паузы и согласование рода для более естественной озвучки."""
    t = text.strip()
    if not t:
        return t

    t = localize_tech_terms_for_tts(t)

    if is_female_voice(speaker):
        replacements = [
            (r"\bЯ готов\b", "Я готова"),
            (r"\bя готов\b", "я готова"),
            (r"\bГотов\b", "Готова"),
            (r"\bготов\b", "готова"),
            (r"\bЯ ваш\b", "Я — ваша"),
            (r"\bваш AI\b", "ваша AI"),
        ]
    else:
        replacements = [
            (r"\bЯ готова\b", "Я готов"),
            (r"\bя готова\b", "я готов"),
            (r"\bГотова\b", "Готов"),
            (r"\bготова\b", "готов"),
            (r"\bЯ — ваша\b", "Я — ваш"),
            (r"\bваша AI\b", "ваш AI"),
        ]
    for pattern, repl in replacements:
        t = re.sub(pattern, repl, t)

    t = re.sub(r"([.!?])\s+", r"\1 ... ", t)
    t = re.sub(r",\s*", ", ", t)
    return t


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+|\s*\.\.\.\s*", text)
    return [p.strip() for p in parts if p.strip() and p.strip() != "..."]
