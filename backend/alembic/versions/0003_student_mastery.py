"""Add durable deterministic student skill mastery."""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_skill_mastery",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id"), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=False),
        sa.Column("skill", sa.String(), nullable=False),
        sa.Column("mastery_estimate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_misconceptions", sa.JSON(), nullable=False),
        sa.Column("last_evidence_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("student_id", "subject", "topic", "skill", name="uq_student_skill_mastery"),
    )
    op.create_index("ix_student_skill_mastery_student_id", "student_skill_mastery", ["student_id"])


def downgrade() -> None:
    op.drop_index("ix_student_skill_mastery_student_id", table_name="student_skill_mastery")
    op.drop_table("student_skill_mastery")
