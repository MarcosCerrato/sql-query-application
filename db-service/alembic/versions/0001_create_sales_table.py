"""create sales table

Revision ID: 0001
Revises:
Create Date: 2026-03-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS makes this migration safe to run against a pre-existing DB
    # that was created before Alembic was introduced.
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id            SERIAL PRIMARY KEY,
            date          VARCHAR,
            week_day      VARCHAR,
            hour          VARCHAR,
            ticket_number VARCHAR,
            waiter        INTEGER,
            product_name  VARCHAR,
            quantity      INTEGER,
            unitary_price NUMERIC(10, 2),
            total         NUMERIC(10, 2)
        )
    """)


def downgrade() -> None:
    op.drop_table("sales")
