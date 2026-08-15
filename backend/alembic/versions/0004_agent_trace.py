"""Add metadata-only agent tracing."""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_trace",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("lesson_sessions.id"), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=True),
        sa.Column("args_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_trace_run_id", "agent_trace", ["run_id"])
    op.create_index("ix_agent_trace_session_id", "agent_trace", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_trace_session_id", table_name="agent_trace")
    op.drop_index("ix_agent_trace_run_id", table_name="agent_trace")
    op.drop_table("agent_trace")
