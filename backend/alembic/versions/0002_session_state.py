"""Add homework outline and ephemeral agent session state."""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in sa.inspect(bind).get_columns("lesson_sessions")}
    if "homework_outline" not in columns:
        op.add_column("lesson_sessions", sa.Column("homework_outline", sa.JSON(), nullable=True))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("lesson_sessions")}
    if "ix_lesson_sessions_mode" not in indexes:
        op.create_index("ix_lesson_sessions_mode", "lesson_sessions", ["mode"])
    op.create_table(
        "agent_session_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("current_goal", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_exercise_index", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("awaiting_response", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("response_target", sa.JSON(), nullable=True),
        sa.Column("hint_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("solved_refs", sa.JSON(), nullable=False),
        sa.Column("annotations", sa.JSON(), nullable=False),
        sa.Column("materials_used", sa.JSON(), nullable=False),
        sa.Column("recent_evaluations", sa.JSON(), nullable=False),
        sa.Column("recommended_next_action", sa.String(), nullable=False, server_default=""),
        sa.Column("applied_evaluation_keys", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("session_id"),
    )
    op.create_index("ix_agent_session_state_session_id", "agent_session_state", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_session_state_session_id", table_name="agent_session_state")
    op.drop_table("agent_session_state")
    op.drop_index("ix_lesson_sessions_mode", table_name="lesson_sessions")
    op.drop_column("lesson_sessions", "homework_outline")
