"""Save each employee's usual monthly salary so it does not have to be typed every month."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0013_employee_salary"
down_revision: str | None = "0012_employee_account_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.add_column(sa.Column("salary", sa.Numeric(14, 2), nullable=True))
        batch.add_column(sa.Column("salary_currency", sa.String(length=3), server_default="SYP", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("employees") as batch:
        batch.drop_column("salary_currency")
        batch.drop_column("salary")
