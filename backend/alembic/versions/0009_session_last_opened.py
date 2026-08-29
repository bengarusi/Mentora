"""Track when a lesson was last opened.

Lesson history reads as a record of where the student has been, so it is ordered
by when each lesson was last opened rather than by when it was created —
reopening an old lesson brings it back to the top of the list.

Existing rows are backfilled from created_at: without a record of past visits,
the order they were created in is the best available answer, and it is exactly
the order the list had before this column existed.
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lesson_sessions",
        sa.Column(
            "last_opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE lesson_sessions SET last_opened_at = created_at "
        "WHERE created_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("lesson_sessions", "last_opened_at")
