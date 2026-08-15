"""Frozen baseline for the schema that predates the homework agent.

This revision deliberately contains explicit DDL. Importing live ORM metadata
here would make the historical baseline change whenever a future model changes,
which makes both fresh upgrades and stamping an existing database unsafe.
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column("math_level", sa.String(), nullable=True),
        sa.Column("english_level", sa.String(), nullable=True),
    )
    op.create_index("ix_students_id", "students", ["id"])
    op.create_index("ix_students_email", "students", ["email"], unique=True)

    op.create_table(
        "lesson_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("subtopic", sa.String(), nullable=False),
        sa.Column("goal_text", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False, server_default="lesson"),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("phase", sa.String(), nullable=False),
        sa.Column("difficulty", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_lesson_sessions_id", "lesson_sessions", ["id"])
    op.create_index("ix_lesson_sessions_student_id", "lesson_sessions", ["student_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_id", "messages", ["id"])
    op.create_index("ix_messages_session_id", "messages", ["session_id"])

    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("set_number", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("correct_answer", sa.Text(), nullable=True),
        sa.Column("solution_steps", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("student_answer", sa.Text(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_assessment_questions_id", "assessment_questions", ["id"])
    op.create_index(
        "ix_assessment_questions_session_id", "assessment_questions", ["session_id"]
    )

    op.create_table(
        "performance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False, unique=True),
        sa.Column("success_level", sa.String(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("practice_sets", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("messages_synced", sa.Integer(), nullable=True),
    )
    op.create_index("ix_performance_id", "performance", ["id"])

    op.create_table(
        "study_materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=True),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("subtopic", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_detail", sa.Text(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("id", "student_id", "session_id", "kind", "subject", "topic", "status"):
        op.create_index(f"ix_study_materials_{column}", "study_materials", [column])

    op.create_table(
        "material_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), sa.ForeignKey("study_materials.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.JSON(), nullable=True),
        sa.Column("embedding_model", sa.String(), nullable=True),
    )
    op.create_index("ix_material_chunks_id", "material_chunks", ["id"])
    op.create_index("ix_material_chunks_material_id", "material_chunks", ["material_id"])


def downgrade() -> None:
    for table in (
        "material_chunks",
        "study_materials",
        "performance",
        "assessment_questions",
        "messages",
        "lesson_sessions",
        "students",
    ):
        op.drop_table(table)
