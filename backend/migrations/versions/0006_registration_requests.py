"""Add guardian registration requests with admin-issued one-time codes."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_registration_requests"
down_revision: str | None = "0005_account_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("children") as batch:
        batch.alter_column("created_by_id", existing_type=sa.Uuid(), nullable=True)
    with op.batch_alter_table("guardian_invitations") as batch:
        batch.alter_column("created_by_id", existing_type=sa.Uuid(), nullable=True)
        batch.add_column(
            sa.Column("auto_approve", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
    op.create_table(
        "registration_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("guardian_name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False, index=True),
        sa.Column("phone", sa.String(length=40), nullable=False),
        sa.Column("child_name", sa.String(length=120), nullable=False),
        sa.Column("child_birth_date", sa.String(length=10), server_default="", nullable=False),
        sa.Column("relationship_to_child", sa.String(length=40), server_default="", nullable=False),
        sa.Column("notes", sa.String(length=1000), server_default="", nullable=False),
        sa.Column("preferred_language", sa.String(length=35), server_default="ar", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False, index=True),
        sa.Column(
            "invitation_id",
            sa.Uuid(),
            sa.ForeignKey("guardian_invitations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email_sent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("registration_requests")
    with op.batch_alter_table("guardian_invitations") as batch:
        batch.drop_column("auto_approve")
