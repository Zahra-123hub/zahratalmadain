"""Store private teacher uploads and report attachments."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_teacher_content"
down_revision: str | None = "0003_teacher_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_content",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "report_id",
            sa.Uuid(),
            sa.ForeignKey("daily_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("original_name", sa.String(length=180), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("contents", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_teacher_content_owner_id", "teacher_content", ["owner_id"])
    op.create_index("ix_teacher_content_report_id", "teacher_content", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_teacher_content_report_id", table_name="teacher_content")
    op.drop_index("ix_teacher_content_owner_id", table_name="teacher_content")
    op.drop_table("teacher_content")
