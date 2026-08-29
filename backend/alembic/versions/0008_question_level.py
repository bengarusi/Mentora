"""Record the lesson difficulty each practice question was written at.

Progress is credited per correctly answered question, and how much a correct
answer is worth depends on the level it was asked at. Reading that back from
lesson_sessions.difficulty would rewrite history the moment a student changes
level, so the level is stamped on the question row instead.

Existing rows are backfilled from their session, which is the level they were in
fact generated at — the column is only new, the fact is not.
"""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_questions", sa.Column("level", sa.String(), nullable=True)
    )
    op.execute(
        """
        UPDATE assessment_questions AS q
        SET level = s.difficulty
        FROM lesson_sessions AS s
        WHERE s.id = q.session_id AND s.difficulty IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("assessment_questions", "level")
