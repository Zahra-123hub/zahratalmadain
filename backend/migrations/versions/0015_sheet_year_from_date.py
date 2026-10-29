"""Weekly and daily sheet rows take their year from their own date (older rows may carry a typed year)."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0015_sheet_year_from_date"
down_revision: str | None = "0014_teacher_posts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_context().as_sql:  # offline SQL script: there is no data to read, nothing to fix
        return
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, week_start, year FROM accounting_entries "
            "WHERE period_type IN ('week', 'day') AND week_start IS NOT NULL"
        )
    ).fetchall()
    for row_id, week_start, year in rows:
        real_year = int(str(week_start)[:4])
        if real_year != year:
            bind.execute(
                sa.text("UPDATE accounting_entries SET year = :year WHERE id = :id"),
                {"year": real_year, "id": row_id},
            )


def downgrade() -> None:
    pass
