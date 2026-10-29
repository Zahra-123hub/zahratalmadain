"""Opening cash balance per currency, so the accounting can work out how much money the kindergarten has."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0016_cash_opening"
down_revision: str | None = "0015_sheet_year_from_date"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cash_openings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("currency", sa.String(length=3), nullable=False, unique=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("start_year", sa.Integer(), nullable=False),
        sa.Column("start_month", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("cash_openings")
