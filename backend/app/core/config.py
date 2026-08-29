from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.4-mini"   # main tutor brain
    LLM_PROVIDER: str = "openai"

    # Agentic Homework Tutor. Kept off by default until the flag is enabled in
    # a target environment; the legacy path remains an atomic fallback.
    AGENT_ENABLED_HOMEWORK: bool = False
    AGENT_MAX_STEPS: int = Field(default=4, ge=1, le=4)
    AGENT_TOOL_TIMEOUT_S: float = Field(default=10.0, gt=0)
    AGENT_MAX_HINT_LEVEL: int = Field(default=4, ge=1)

    # Voice I/O models — kept separate so the tutor brain can evolve
    # independently of speech-to-text / text-to-speech.
    # Override any of these in backend/.env without touching service code.
    OPENAI_STT_MODEL: str = "gpt-4o-transcribe"
    # ISO-639-1 language spoken by the student. Pins transcription to one
    # language so short or noisy clips are not misdetected as another tongue.
    # Set empty to let the model auto-detect.
    OPENAI_STT_LANGUAGE: str = "en"
    # Recordings smaller than this are treated as silence and not transcribed.
    # Disabled by default (0): a short spoken answer like "eight" is a valid
    # turn. Raise it only if empty-audio hallucinations become a problem.
    STT_MIN_AUDIO_BYTES: int = 0
    OPENAI_TTS_MODEL: str = "gpt-4o-mini-tts"
    OPENAI_TTS_VOICE: str = "alloy"

    # Vision model used to read text off uploaded images (photographed
    # homework, scanned worksheets). Must be a vision-capable model.
    OPENAI_VISION_MODEL: str = "gpt-4o-mini"

    # Local-demo only: write every prompt sent to the model to logs/prompts/.
    # Off by default; the files contain full student and material text.
    LLM_DEBUG_DUMP_PROMPTS: bool = False

    # ---- visual board explanations ----
    # Off by default until enabled in a target environment. Practice is fully
    # functional without it: the list endpoint reports enabled=false and the UI
    # renders no board action, while the generate/fetch endpoints 404.
    BOARD_EXPLANATION_ENABLED: bool = False
    # Caps how much of one board we keep. Bounds modal length and prompt cost;
    # blocks beyond the budget are dropped, never a reason to fail a board.
    BOARD_MAX_BLOCKS: int = Field(default=6, ge=1, le=12)
    # Board generation is one structured JSON call, kept on its own model setting
    # so it can be upgraded independently of the tutor brain.
    OPENAI_BOARD_MODEL: str = "gpt-5.4-mini"
    # How much of the boards already shown may be recalled into a later chat
    # prompt. Only a compact digest is carried, never the full spec.
    BOARD_DIGEST_CHAR_BUDGET: int = 700
    # How many recent boards the tutor keeps in mind. Two covers "the one we just
    # looked at" and "the one before"; more is prompt cost for little gain.
    BOARD_DIGEST_LIMIT: int = 2

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
