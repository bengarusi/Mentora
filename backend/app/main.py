import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
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