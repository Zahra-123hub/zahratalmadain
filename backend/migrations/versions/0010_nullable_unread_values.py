"""Allow empty values for fields that could not be read from the paper tables.

Unreadable amounts and dates are stored as NULL (never as 0 or an invented date) together with
needs_review and the raw text.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_nullable_unread_values"
down_revision: str | None = "0009_accounting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fee_charges") as batch:
        batch.alter_column("amount", existing_type=sa.Numeric(14, 2), nullable=True)
        batch.add_column(sa.Column("note", sa.String(length=500), server_default="", nullable=False))
    with op.batch_alter_table("fee_payments") as batch:
        batch.alter_column("paid_on", existing_type=sa.Date(), nullable=True)
    with op.batch_alter_table("salary_lines") as batch:
        for column in ("base", "bonus", "advance", "deduction"):
            batch.alter_column(column, existing_type=sa.Numeric(14, 2), nullable=True)


def downgrade() -> None:
    # Rows with empty values would violate the old constraints; they are left for manual review.
    op.execute("UPDATE fee_charges SET amount = 0 WHERE amount IS NULL")
    op.execute("UPDATE fee_payments SET paid_on = DATE('2000-01-01') WHERE paid_on IS NULL")
    for column in ("base", "bonus", "advance", "deduction"):
        op.execute(f"UPDATE salary_lines SET {column} = 0 WHERE {column} IS NULL")
    with op.batch_alter_table("salary_lines") as batch:
        for column in ("base", "bonus", "advance", "deduction"):
            batch.alter_column(column, existing_type=sa.Numeric(14, 2), nullable=False)
    with op.batch_alter_table("fee_payments") as batch:
        batch.alter_column("paid_on", existing_type=sa.Date(), nullable=False)
    with op.batch_alter_table("fee_charges") as batch:
        batch.drop_column("note")
        batch.alter_column("amount", existing_type=sa.Numeric(14, 2), nullable=False)
