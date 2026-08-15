"""Add visual board explanations for practice questions."""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "board_explanations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column(
            "question_id", sa.Integer(), sa.ForeignKey("assessment_questions.id"), nullable=False
        ),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # At most one board per question per mode: this is what makes reopening
        # free and stops a board carrying over to another question.
        sa.UniqueConstraint("question_id", "mode", name="uq_board_question_mode"),
    )
    op.create_index("ix_board_explanations_id", "board_explanations", ["id"])
    op.create_index("ix_board_explanations_session_id", "board_explanations", ["session_id"])
    op.create_index("ix_board_explanations_question_id", "board_explanations", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_board_explanations_question_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_session_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_id", table_name="board_explanations")
    op.drop_table("board_explanations")
