"""Link registration requests to the parent account created from them."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_registration_account_link"
down_revision: str | None = "0006_registration_requests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("registration_requests") as batch:
        batch.add_column(sa.Column("account_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_registration_requests_account_id",
            "accounts",
            ["account_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("registration_requests") as batch:
        batch.drop_constraint("fk_registration_requests_account_id", type_="foreignkey")
        batch.drop_column("registered_at")
        batch.drop_column("account_id")
