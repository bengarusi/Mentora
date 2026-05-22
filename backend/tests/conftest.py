import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all models on Base.metadata)
from app.api.dependencies import get_current_student, get_llm
from app.db.database import Base, get_db
from app.main import app
from app.models.student import Student
from app.core.security import hash_password
from tests.fake_llm import FakeLLMProvider


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def db_session(session_factory):
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_llm] = lambda: FakeLLMProvider()
    # NOTE: no `with` — avoids triggering the lifespan (which would hit Postgres).
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_student(db, email="kid@example.com", password="secret123") -> Student:
    student = Student(
        full_name="Test Kid",
        email=email,
        password_hash=hash_password(password),
        age=10,
        grade="5",
        math_level="beginner",
        english_level="beginner",
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def auth_headers(client, email="kid@example.com", password="secret123") -> dict:
    register_payload = {
        "full_name": "Test Kid",
        "email": email,
        "password": password,
        "age": 10,
        "grade": "5",
    }
    client.post("/auth/register", json=register_payload)
    resp = client.post(
        "/auth/login", data={"username": email, "password": password}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
