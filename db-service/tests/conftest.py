"""Shared fixtures for db-service tests.

DATABASE_URL must be set before db-service modules are imported,
because `engine = create_engine(settings.database_url)` runs at import time.
We achieve this by patching the env var at the top of this file (collected
before any test module is imported by pytest).
"""
import os
import sys

# ── Set env vars before any service module is imported ────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///file:testmemdb?mode=memory&cache=shared&uri=true"

# Ensure the service root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sqlalchemy import create_engine, text


@pytest.fixture(scope="session")
def sqlite_engine():
    """SQLite shared in-memory engine with a minimal 'sales' table.

    Using a named shared cache URI so all connections from this engine
    (and the patched module engine) see the same in-memory database.
    """
    uri = "sqlite:///file:testmemdb?mode=memory&cache=shared&uri=true"
    engine = create_engine(uri, connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE sales (
                id      INTEGER PRIMARY KEY,
                product TEXT NOT NULL,
                amount  REAL NOT NULL,
                region  TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            INSERT INTO sales (id, product, amount, region) VALUES
            (1, 'Widget', 100.0, 'North'),
            (2, 'Gadget', 250.0, 'South'),
            (3, 'Widget', 75.5,  'North')
        """))
        conn.commit()
    return engine
