"""Настройки приложения из переменных окружения (.env)."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env в корне репозитория (на уровень выше backend/app)
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """Конфигурация: БД, LLM, CORS, пути к записям."""
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.is_file() else ".env",
        extra="ignore",
    )

    # Локально без Docker: sqlite+aiosqlite:///./data/interview.db
    database_url: str = "sqlite+aiosqlite:///./data/interview.db"
    # LLM (OpenAI-совместимый API: DeepSeek, GigaChat и др.)
    llm_provider: str = "deepseek"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    # Обратная совместимость с .env
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    recordings_dir: str = "./recordings"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    mock_ai: bool = False
    # TTS: Silero (локально, ru). Голоса: baya, kseniya (мягче), xenia, aidar, eugene
    tts_enabled: bool = True
    # silero — офлайн ru; edge — ru+en; yandex — SpeechKit (облако, см. docs/YANDEX_STT_SETUP.md)
    tts_engine: str = "edge"
    tts_voice: str = "kseniya"
    tts_speed: float = 0.88  # < 1 — медленнее и спокойнее (Silero); для Yandex см. YANDEX_TTS_SPEED
    tts_edge_voice: str = "ru-RU-SvetlanaNeural"

    # SMTP для отчётов после интервью (пустой SMTP_HOST — только лог в консоль)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False  # True или порт 465 — для Mail.ru
    email_from: str = ""
    email_from_name: str = "AI Technical Interview"

    # STT: faster-whisper (локально), openai или yandex (облако)
    stt_provider: str = "whisper"  # whisper | openai | yandex
    stt_model: str = "small"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"
    stt_language: str = "ru"
    stt_beam_size: int = 5
    stt_cpu_threads: int = 0  # 0 = все доступные ядра
    stt_vad_filter: bool = True
    stt_max_audio_bytes: int = 12_000_000  # ~10–12 мин webm/opus
    stt_initial_prompt: str = (
        "Техническое собеседование программиста. Ответ кандидата на русском языке. "
        "SQL, PostgreSQL, Python, JavaScript, TypeScript, FastAPI, LangChain, Qdrant, "
        "Kafka, Docker, Kubernetes, Redis, Git, алгоритмы, базы данных, API, микросервисы."
    )
    # OpenAI Whisper API (STT_PROVIDER=openai): ~$0.006/мин, до 25 МБ за запрос
    openai_stt_api_key: str = ""
    openai_stt_base_url: str = "https://api.openai.com/v1"
    openai_stt_model: str = "whisper-1"
    openai_stt_timeout_sec: float = 120.0

    # Yandex SpeechKit STT (STT_PROVIDER=yandex): ~0.16 ₽ / 15 с синхронного API
    yandex_folder_id: str = ""
    yandex_api_key: str = ""
    yandex_stt_lang: str = "ru-RU"
    yandex_stt_topic: str = ""  # general | maps | dates | names | numbers
    yandex_stt_timeout_sec: float = 120.0
    yandex_stt_chunk_seconds: float = 25.0  # длинные ответы режутся на фрагменты
    yandex_stt_sync_max_seconds: float = 28.0
    yandex_stt_max_chunks: int = 120  # до ~50 мин речи при chunk=25

    # Yandex SpeechKit TTS (TTS_ENGINE=yandex): ~0.16 ₽ / 1000 символов
    yandex_tts_voice: str = "alena"  # alena, marina, jane, filipp, …; premium: alena:premium
    yandex_tts_lang: str = "ru-RU"
    yandex_tts_format: str = "mp3"  # mp3 | oggopus | lpcm
    yandex_tts_speed: float = 0.95  # 0.1–3.0; чуть медленнее звучит спокойнее
    yandex_tts_emotion: str = "good"  # good | neutral (зависит от голоса); пусто — по умолчанию API
    yandex_tts_timeout_sec: float = 90.0

    # Дополнительная стенограмма «всего интервью» из полной аудиодорожки.
    # Нужна, чтобы в отчёте учитывались рассуждения во время набора кода,
    # даже если кандидат не нажимал «Ответить» в этот момент.
    transcribe_full_session_audio: bool = True
    # Ограничение длительности (сек) для полной транскрипции. 0 = без лимита.
    transcribe_full_session_audio_max_seconds: int = 900

    # Тестовый режим: 2 ответа кандидата → завершение интервью
    interview_test_mode: bool = False
    interview_test_max_turns: int = 2

    # Доступ к админке / админским API (HTTP Basic) — задайте через .env
    admin_username: str = "admin"
    admin_password: str = "change-me"

    # Публичный URL API (ссылки на видео в письмах). При туннеле на :5173 — тот же домен, что и UI.
    public_base_url: str = "http://localhost:8000"
    # Публичный URL интерфейса (ссылка кандидату). Пусто — выводится из public_base_url (:8000 → :5173).
    public_frontend_url: str = ""

    # Автомонтаж MP4 после интервью (экран слева, камера справа)
    montage_enabled: bool = True
    # True — пересобирать даже если montage.mp4 уже есть (MONTAGE_FORCE_REBUILD=true в .env)
    montage_force_rebuild: bool = False
    # Текст в первом письме: «видео примерно через N часов»
    montage_email_delay_hours: int = 2

    @field_validator("smtp_password", mode="before")
    @classmethod
    def _strip_smtp_password(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().strip('"').strip("'")
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_tts_voice(self) -> str:
        """Имя голоса для родовой грамматики и prepare_for_tts."""
        engine = (self.tts_engine or "silero").lower()
        if engine == "yandex":
            v = (self.yandex_tts_voice or "alena").strip()
            return v or "alena"
        if engine == "edge":
            ev = (self.tts_edge_voice or "").lower()
            if any(m in ev for m in ("dmitry", "pavel", "aleksey", "alexey")):
                return "aidar"
            return "kseniya"
        return (self.tts_voice or "kseniya").strip() or "kseniya"

    @property
    def frontend_public_url(self) -> str:
        """Базовый URL UI для ссылок кандидату (домен или localhost:5173)."""
        if self.public_frontend_url.strip():
            return self.public_frontend_url.strip().rstrip("/")
        base = self.public_base_url.strip().rstrip("/")
        if ":8000" in base:
            return base.replace(":8000", ":5173", 1)
        return base or "http://localhost:5173"


def fresh_settings() -> Settings:
    """Новый экземпляр настроек из .env (без lru_cache — для ссылок после смены PUBLIC_*)."""
    return Settings()


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if not (settings.llm_api_key or settings.deepseek_api_key):
        settings.mock_ai = True
    if not settings.llm_base_url:
        settings.llm_base_url = settings.deepseek_base_url
    if not settings.llm_model:
        settings.llm_model = settings.deepseek_model
    if not settings.llm_api_key:
        settings.llm_api_key = settings.deepseek_api_key
    return settings
