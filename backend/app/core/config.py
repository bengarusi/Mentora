from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"   # main tutor brain
    LLM_PROVIDER: str = "openai"

    # Voice I/O models — kept separate so the tutor brain can evolve
    # independently of speech-to-text / text-to-speech.
    # Override any of these in backend/.env without touching service code.
    OPENAI_STT_MODEL: str = "gpt-4o-transcribe"
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "alloy"

    # Vision model used to read text off uploaded images (photographed
    # homework, scanned worksheets). Must be a vision-capable model.
    OPENAI_VISION_MODEL: str = "gpt-4o-mini"

    # ---- study materials / homework uploads ----
    MATERIAL_STORAGE_DIR: str = "storage/materials"
    MATERIAL_MAX_UPLOAD_MB: int = 20
    # How much retrieved material text may be injected into one tutor prompt.
    # Caps prompt cost and stops a large upload from crowding out the lesson.
    MATERIAL_CONTEXT_CHAR_BUDGET: int = 4000

    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    LOG_LEVEL: str = "INFO"
    LOG_DIR: str | None = None  # None -> backend/logs/ (resolved in logging.config)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
