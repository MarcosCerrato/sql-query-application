"""Alter hour column from VARCHAR to TIME."""
from alembic import op

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE sales
        ALTER COLUMN hour TYPE TIME
        USING hour::TIME
    """)


def downgrade():
    op.execute("""
        ALTER TABLE sales
        ALTER COLUMN hour TYPE VARCHAR
        USING TO_CHAR(hour, 'HH24:MI')
    """)
