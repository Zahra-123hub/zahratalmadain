"""Add employees, salary lines, accounting sheet rows and review flags for imported fees."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0009_accounting"
down_revision: str | None = "0008_fees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fee_charges") as batch:
        batch.add_column(sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch.add_column(sa.Column("raw_text", sa.String(length=300), server_default="", nullable=False))
        batch.add_column(sa.Column("source", sa.String(length=120), server_default="", nullable=False))
    op.create_table(
        "employees",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, index=True),
        sa.Column("job_title", sa.String(length=80), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "salary_lines",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("employee_id", sa.Uuid(), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("month", sa.Integer(), nullable=False, index=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("base", sa.Numeric(14, 2), nullable=False),
        sa.Column("bonus", sa.Numeric(14, 2), nullable=False),
        sa.Column("advance", sa.Numeric(14, 2), nullable=False),
        sa.Column("deduction", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("raw_text", sa.String(length=300), server_default="", nullable=False),
        sa.Column("source", sa.String(length=120), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("employee_id", "year", "month", "currency", name="uq_salary_period"),
    )
    op.create_table(
        "accounting_entries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("period_type", sa.String(length=5), nullable=False, index=True),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("month", sa.Integer(), server_default="0", nullable=False),
        sa.Column("week_start", sa.Date(), nullable=True, index=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("item_key", sa.String(length=20), nullable=False),
        sa.Column("item_label", sa.String(length=120), server_default="", nullable=False),
        sa.Column("details", sa.String(length=500), server_default="", nullable=False),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column("income", sa.Numeric(14, 2), nullable=False),
        sa.Column("expense", sa.Numeric(14, 2), nullable=False),
        sa.Column("manual", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("accounting_entries")
    op.drop_table("salary_lines")
    op.drop_table("employees")
    with op.batch_alter_table("fee_charges") as batch:
        batch.drop_column("source")
        batch.drop_column("raw_text")
        batch.drop_column("needs_review")
