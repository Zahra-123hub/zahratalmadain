"""Add the accountant role, children classes, monthly fees, payments and audit log."""

from typing import Sequence
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "0008_fees"
down_revision: str | None = "0007_registration_account_link"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("children") as batch:
        batch.add_column(
            sa.Column("class_name", sa.String(length=60), server_default="", nullable=False)
        )
    op.create_table(
        "fee_charges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "child_id",
            sa.Uuid(),
            sa.ForeignKey("children.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("year", sa.Integer(), nullable=False, index=True),
        sa.Column("month", sa.Integer(), nullable=False, index=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("child_id", "year", "month", "currency", name="uq_fee_charge_period"),
    )
    op.create_table(
        "fee_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "charge_id",
            sa.Uuid(),
            sa.ForeignKey("fee_charges.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("receipt_no", sa.String(length=40), nullable=True),
        sa.Column("note", sa.String(length=500), server_default="", nullable=False),
        sa.Column(
            "created_by_id",
            sa.Uuid(),
            sa.ForeignKey("accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by_name", sa.String(length=80), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_fee_payment_receipt_active",
        "fee_payments",
        ["receipt_no"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND receipt_no IS NOT NULL"),
        sqlite_where=sa.text("deleted_at IS NULL AND receipt_no IS NOT NULL"),
    )
    op.create_table(
        "fee_audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=80), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=40), nullable=False),
        sa.Column("details", sa.String(length=1000), server_default="", nullable=False),
    )

    # Role "accountant" with the fees.manage permission.
    connection = op.get_bind()
    role_id, permission_id = uuid.uuid4(), uuid.uuid4()
    roles = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    permissions = sa.table("permissions", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    links = sa.table(
        "role_permissions", sa.column("role_id", sa.Uuid()), sa.column("permission_id", sa.Uuid())
    )
    if not connection.execute(sa.select(roles.c.id).where(roles.c.name == "accountant")).first():
        op.bulk_insert(roles, [{"id": role_id, "name": "accountant"}])
        existing = connection.execute(
            sa.select(permissions.c.id).where(permissions.c.name == "fees.manage")
        ).first()
        if existing:
            permission_id = existing[0]
        else:
            op.bulk_insert(permissions, [{"id": permission_id, "name": "fees.manage"}])
        op.bulk_insert(links, [{"role_id": role_id, "permission_id": permission_id}])


def downgrade() -> None:
    op.drop_table("fee_audit_log")
    op.drop_index("uq_fee_payment_receipt_active", table_name="fee_payments")
    op.drop_table("fee_payments")
    op.drop_table("fee_charges")
    with op.batch_alter_table("children") as batch:
        batch.drop_column("class_name")
