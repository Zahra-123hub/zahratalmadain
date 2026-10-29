"""Add explicit platform account approval states."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_account_approval"
down_revision: str | None = "0004_teacher_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column(
            "approval_status",
            sa.String(length=20),
            server_default="active",
            nullable=False,
        ),
    )
def downgrade() -> None:
    op.drop_column("accounts", "approval_status")
