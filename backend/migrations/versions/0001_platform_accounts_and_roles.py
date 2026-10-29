"""Create platform accounts, roles, and permissions."""

from typing import Sequence
import uuid

from alembic import op
import sqlalchemy as sa

revision: str = "0001_platform_accounts_and_roles"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLE_PERMISSIONS = {
    "admin": (
        "accounts.manage",
        "children.manage",
        "groups.manage",
        "reports.create",
        "reports.review",
        "reports.read",
        "settings.manage",
        "subscriptions.manage",
    ),
    "manager": ("children.manage", "groups.manage", "reports.review"),
    "teacher": ("reports.create",),
    "parent": ("reports.read",),
}


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(length=80), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("preferred_language", sa.String(length=35), server_default="ar", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=40), nullable=False, unique=True),
    )
    op.create_table(
        "permissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(length=80), nullable=False, unique=True),
    )
    op.create_table(
        "account_roles",
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    )
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Uuid(), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", sa.Uuid(), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    role_table = sa.table("roles", sa.column("id", sa.Uuid()), sa.column("name", sa.String()))
    permission_table = sa.table(
        "permissions", sa.column("id", sa.Uuid()), sa.column("name", sa.String())
    )
    role_permission_table = sa.table(
        "role_permissions",
        sa.column("role_id", sa.Uuid()),
        sa.column("permission_id", sa.Uuid()),
    )
    roles = {name: uuid.uuid4() for name in ROLE_PERMISSIONS}
    permissions = sorted({permission for values in ROLE_PERMISSIONS.values() for permission in values})
    permission_ids = {name: uuid.uuid4() for name in permissions}
    op.bulk_insert(
        role_table,
        [{"id": role_id, "name": name} for name, role_id in roles.items()],
    )
    op.bulk_insert(
        permission_table,
        [{"id": permission_ids[name], "name": name} for name in permissions],
    )
    op.bulk_insert(
        role_permission_table,
        [
            {"role_id": roles[role], "permission_id": permission_ids[permission]}
            for role, assigned in ROLE_PERMISSIONS.items()
            for permission in assigned
        ],
    )


def downgrade() -> None:
    op.drop_table("role_permissions")
    op.drop_table("account_roles")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("accounts")
