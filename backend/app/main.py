from fastapi import FastAPI
from app.db.database import Base, engine
from app.api import sessionController as session
from app.api import authController as auth
from app.models import Student, LessonSession, Message  # noqa
from app.api import messageController as message

app = FastAPI(title="Mentora API")

Base.metadata.create_all(bind=engine)

app.include_router(auth.router)
app.include_router(session.router)
app.include_router(message.router)

@app.get("/")
def root():
    return {"message": "Mentora backend is running"}