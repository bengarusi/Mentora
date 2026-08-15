import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.db.database import Base


def test_alembic_upgrade_head_on_empty_database_matches_metadata(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    env = {**os.environ, "DATABASE_URL": database_url}
    backend = Path(__file__).parents[1]

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    actual = set(inspect(create_engine(database_url)).get_table_names())
    assert actual == set(Base.metadata.tables) | {"alembic_version"}

    check = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
    )
    assert check.returncode == 0, check.stdout + check.stderr


def test_existing_unversioned_baseline_can_be_verified_stamped_and_upgraded(
    tmp_path,
):
    database_url = f"sqlite:///{tmp_path / 'existing.db'}"
    env = {**os.environ, "DATABASE_URL": database_url}
    backend = Path(__file__).parents[1]

    def alembic(*args: str) -> None:
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=backend,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    # Build the exact pre-agent schema and preserve representative data, then
    # remove only Alembic's marker to simulate the existing local Mentora DB.
    alembic("upgrade", "0001")
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO students "
                "(id, full_name, email, password_hash, age, grade) "
                "VALUES (7, 'Existing Kid', 'existing@example.com', 'hash', 10, '5')"
            )
        )
        conn.execute(text("DROP TABLE alembic_version"))

    # This is the documented existing-DB procedure: inspect compatibility,
    # stamp the matching frozen baseline, and only then apply new revisions.
    alembic("stamp", "0001")
    alembic("upgrade", "head")

    inspector = inspect(engine)
    assert "homework_outline" in {
        column["name"] for column in inspector.get_columns("lesson_sessions")
    }
    assert "ix_lesson_sessions_mode" in {
        index["name"] for index in inspector.get_indexes("lesson_sessions")
    }
    assert {
        "agent_session_state",
        "student_skill_mastery",
        "agent_trace",
    }.issubset(inspector.get_table_names())
    with engine.connect() as conn:
        assert conn.execute(
            text("SELECT email FROM students WHERE id = 7")
        ).scalar_one() == "existing@example.com"


def test_baseline_revision_does_not_import_live_orm_metadata():
    source = (
        Path(__file__).parents[1] / "alembic/versions/0001_existing_schema.py"
    ).read_text()
    assert "Base.metadata" not in source
    assert "import app.models" not in source


def test_application_startup_does_not_compete_with_alembic_for_schema_ownership():
    source = (Path(__file__).parents[1] / "app/main.py").read_text()
    assert "create_all" not in source
    assert "ALTER TABLE" not in source
