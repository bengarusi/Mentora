"""Remove the redundant non-unique agent session-state index.

The unique constraint on ``session_id`` already supplies the lookup index and
matches the one-state-row-per-session ownership rule.
"""

from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_agent_session_state_session_id", table_name="agent_session_state")


def downgrade() -> None:
    op.create_index(
        "ix_agent_session_state_session_id",
        "agent_session_state",
        ["session_id"],
        unique=False,
    )
