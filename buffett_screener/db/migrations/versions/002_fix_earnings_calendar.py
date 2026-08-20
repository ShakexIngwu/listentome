"""
db/migrations/versions/002_fix_earnings_calendar.py
Fix earnings_calendar schema to match code expectations.
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename expected_date to earnings_date
    op.alter_column(
        'earnings_calendar',
        'expected_date',
        new_column_name='earnings_date',
    )

    # Add time_of_day column
    op.add_column(
        'earnings_calendar',
        sa.Column('time_of_day', sa.VARCHAR(20), nullable=True),
    )


def downgrade() -> None:
    # Drop time_of_day column
    op.drop_column('earnings_calendar', 'time_of_day')

    # Rename earnings_date back to expected_date
    op.alter_column(
        'earnings_calendar',
        'earnings_date',
        new_column_name='expected_date',
    )
