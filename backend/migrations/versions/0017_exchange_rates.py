"""Exchange rates (Syrian pounds per US dollar) so amounts can be converted between the two currencies."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0017_exchange_rates"
down_revision: str | None = "0016_cash_opening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("syp_per_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_by", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exchange_rates_effective_date", "exchange_rates", ["effective_date"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_exchange_rates_effective_date", table_name="exchange_rates")
    op.drop_table("exchange_rates")
