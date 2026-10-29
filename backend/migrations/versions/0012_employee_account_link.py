"""Link saved staff names (employees) to their platform accounts."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0012_employee_account_link"
down_revision: str | None = "0011_who_paid_who_spent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_employees_account_id", "accounts", ["account_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_unique_constraint("uq_employees_account_id", ["account_id"])


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.drop_constraint("uq_employees_account_id", type_="unique")
        batch.drop_constraint("fk_employees_account_id", type_="foreignkey")
        batch.drop_column("account_id")
