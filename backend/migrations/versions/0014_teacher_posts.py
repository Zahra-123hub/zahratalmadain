"""Teacher posts: general (all parents) or private to one child's parents, with file attachments."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0014_teacher_posts"
down_revision: str | None = "0013_employee_salary"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "teacher_posts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("author_id", sa.Uuid(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("child_id", sa.Uuid(), sa.ForeignKey("children.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=3000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_teacher_posts_author_id", "teacher_posts", ["author_id"])
    op.create_index("ix_teacher_posts_child_id", "teacher_posts", ["child_id"])
    op.create_index("ix_teacher_posts_created_at", "teacher_posts", ["created_at"])
    with op.batch_alter_table("teacher_content") as batch:
        batch.add_column(sa.Column("post_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_teacher_content_post_id", "teacher_posts", ["post_id"], ["id"], ondelete="CASCADE")
        batch.create_index("ix_teacher_content_post_id", ["post_id"])


def downgrade() -> None:
    with op.batch_alter_table("teacher_content") as batch:
        batch.drop_index("ix_teacher_content_post_id")
        batch.drop_constraint("fk_teacher_content_post_id", type_="foreignkey")
        batch.drop_column("post_id")
    op.drop_table("teacher_posts")
