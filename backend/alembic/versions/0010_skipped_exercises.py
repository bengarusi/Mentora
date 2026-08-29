"""Remember which homework exercises the student parked for later.

A student who cannot do exercise 2 should be able to move on and be brought back
to it once the rest is done, so a skipped exercise has to be distinguishable
from both a solved one and one not yet reached.

Existing rows start with nothing skipped, which is what they meant: before this
column the only way past an exercise was to solve it.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_session_state",
        sa.Column(
            "skipped_refs",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_session_state", "skipped_refs")
