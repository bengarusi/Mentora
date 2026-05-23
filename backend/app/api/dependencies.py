from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.llm.factory import get_llm_provider
from app.llm.provider import LLMProvider
from app.models.student import Student
from app.repositories.student_repo import StudentRepository
from app.services.tutor_service import TutorService
from app.services.voice_service import VoiceService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_student(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Student:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_exception
    student = StudentRepository(db).get(int(payload["sub"]))
    if student is None:
        raise credentials_exception
    return student


def get_llm() -> LLMProvider:
    """Dependency seam — tests override this to inject a fake provider."""
    return get_llm_provider()


def get_tutor_service(
    db: Session = Depends(get_db),
    student: Student = Depends(get_current_student),
    llm: LLMProvider = Depends(get_llm),
) -> TutorService:
    return TutorService(db, llm, student)


def get_voice_service() -> VoiceService:
    """Dependency seam for the audio I/O layer — tests can override this."""
    return VoiceService()
