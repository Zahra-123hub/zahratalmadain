"""Record who paid (payer), who spent/received (accounting rows) and who handed out salaries."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_who_paid_who_spent"
down_revision: str | None = "0010_nullable_unread_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("fee_payments") as batch:
        batch.add_column(sa.Column("payer_name", sa.String(length=120), server_default="", nullable=False))
    with op.batch_alter_table("accounting_entries") as batch:
        batch.add_column(sa.Column("person", sa.String(length=120), server_default="", nullable=False))
        batch.add_column(sa.Column("entered_by", sa.String(length=80), server_default="", nullable=False))
    with op.batch_alter_table("salary_lines") as batch:
        batch.add_column(sa.Column("paid_by", sa.String(length=120), server_default="", nullable=False))
        batch.add_column(sa.Column("recorded_by", sa.String(length=80), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("salary_lines") as batch:
        batch.drop_column("recorded_by")
        batch.drop_column("paid_by")
    with op.batch_alter_table("accounting_entries") as batch:
        batch.drop_column("entered_by")
        batch.drop_column("person")
    with op.batch_alter_table("fee_payments") as batch:
        batch.drop_column("payer_name")
