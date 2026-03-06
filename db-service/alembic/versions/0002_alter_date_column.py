"""Alter date column from VARCHAR to DATE."""
from alembic import op

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE sales
        ALTER COLUMN date TYPE DATE
        USING TO_DATE(date, 'MM/DD/YYYY')
    """)


def downgrade():
    op.execute("""
        ALTER TABLE sales
        ALTER COLUMN date TYPE VARCHAR
        USING TO_CHAR(date, 'MM/DD/YYYY')
    """)
