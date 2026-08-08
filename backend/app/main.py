import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.core.logging import LoggingMiddleware, setup_logging
from app.db.database import Base, engine
from app.api import sessionController as session
from app.api import authController as auth
from app.api import messageController as message
from app.api import tutorController as tutor
from app.api import progressController as progress
from app.models import (  # noqa
    Student,
    LessonSession,
    Message,
    AssessmentQuestion,
    Performance,
)

setup_logging()
logging.getLogger("app.main").info(
    "application startup service=mentora-api status=up"
)


def _ensure_dev_schema() -> None:
    """Dev-only, idempotent migration for the mandatory `subtopic` column.

    `create_all` never alters existing tables, so an older dev DB created before
    `LessonSession.subtopic` existed would be missing the column. This adds it,
    backfills nulls from `topic`, and enforces NOT NULL — all no-ops on a fresh
    DB. Guarded so a failure can never block startup. (Postgres syntax.)"""
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE lesson_sessions "
                    "ADD COLUMN IF NOT EXISTS subtopic VARCHAR"
                )
            )
            conn.execute(
                text(
                    "UPDATE lesson_sessions SET subtopic = topic "
                    "WHERE subtopic IS NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE lesson_sessions "
                    "ALTER COLUMN subtopic SET NOT NULL"
                )
            )
            conn.execute(
                text(
                    "ALTER TABLE lesson_sessions "
                    "ADD COLUMN IF NOT EXISTS difficulty VARCHAR"
                )
            )
    except Exception:  # noqa: BLE001 - never block startup on a dev migration
        logging.getLogger("app.main").warning(
            "dev schema check for lesson_sessions.subtopic skipped", exc_info=True
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_dev_schema()
    yield


app = FastAPI(title="Mentora API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# Registered AFTER CORS so it is the outermost middleware: it logs every request
# (including CORS preflight OPTIONS) and times the full request, while CORS runs
# inside it and still adds its Access-Control-* headers.
app.add_middleware(LoggingMiddleware)

app.include_router(auth.router)
app.include_router(session.router)
app.include_router(message.router)
app.include_router(tutor.router)
app.include_router(progress.router)

@app.get("/")
def root():
    return {"message": "Mentora backend is running"}