"""Re-anchor board explanations from questions to chat messages.

Boards moved from the practice flow into the lesson itself, so the anchor
changed from (question_id, mode) to either a tutor message or a graded question,
and the method/full mode split disappeared with it.

This drops and recreates the table rather than altering it. 0006 shipped and was
enabled in the same change as this rework, so no board predates it that anyone
would want to keep, and a stored BoardSpec from 0006 lacks the per-block
narration this version requires — carrying rows across would leave boards that
cannot be played.
"""

from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _create_current(table_name: str) -> None:
    op.create_table(
        table_name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column(
            "question_id", sa.Integer(), sa.ForeignKey("assessment_questions.id"), nullable=True
        ),
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
    )
    op.create_index(f"ix_{table_name}_id", table_name, ["id"])
    op.create_index(f"ix_{table_name}_session_id", table_name, ["session_id"])
    # Unique per anchor: replaying a board never regenerates it, and a board can
    # never be reused for a different message or question.
    op.create_index(f"ix_{table_name}_message_id", table_name, ["message_id"], unique=True)
    op.create_index(f"ix_{table_name}_question_id", table_name, ["question_id"], unique=True)


def upgrade() -> None:
    op.drop_index("ix_board_explanations_question_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_session_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_id", table_name="board_explanations")
    op.drop_table("board_explanations")
    _create_current("board_explanations")


def downgrade() -> None:
    op.drop_index("ix_board_explanations_question_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_message_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_session_id", table_name="board_explanations")
    op.drop_index("ix_board_explanations_id", table_name="board_explanations")
    op.drop_table("board_explanations")

    # Restore the 0006 shape.
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
        sa.UniqueConstraint("question_id", "mode", name="uq_board_question_mode"),
    )
    op.create_index("ix_board_explanations_id", "board_explanations", ["id"])
    op.create_index("ix_board_explanations_session_id", "board_explanations", ["session_id"])
    op.create_index("ix_board_explanations_question_id", "board_explanations", ["question_id"])
