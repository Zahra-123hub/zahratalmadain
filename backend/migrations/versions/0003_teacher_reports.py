"""Add teacher assignments and child reports."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_teacher_reports"
down_revision: str | None = "0002_guardian_access"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_child_links",
        sa.Column(
            "account_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "child_id",
            sa.Uuid(),
            sa.ForeignKey("children.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "daily_reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "child_id",
            sa.Uuid(),
            sa.ForeignKey("children.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=3000), nullable=False),
        sa.Column("language", sa.String(length=35), server_default="ar", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_daily_reports_child_id", "daily_reports", ["child_id"])
    op.create_index("ix_daily_reports_author_id", "daily_reports", ["author_id"])
    op.create_index("ix_daily_reports_status", "daily_reports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_daily_reports_status", table_name="daily_reports")
    op.drop_index("ix_daily_reports_author_id", table_name="daily_reports")
    op.drop_index("ix_daily_reports_child_id", table_name="daily_reports")
    op.drop_table("daily_reports")
    op.drop_table("teacher_child_links")
