"""Shared fixtures for model-service tests."""
import sys
import os
import pytest

# Ensure the service root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Set required env vars before any import
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")
os.environ.setdefault("OLLAMA_MODEL", "qwen2.5-coder:7b")
os.environ.setdefault("DB_SERVICE_URL", "http://localhost:8001")


@pytest.fixture
def sample_schema():
    return {
        "table": "sales",
        "columns": [
            {"name": "id", "type": "INTEGER", "sample_values": ["1", "2", "3"]},
            {"name": "product", "type": "VARCHAR", "sample_values": ["Widget", "Gadget"]},
            {"name": "amount", "type": "NUMERIC", "sample_values": ["100.00", "250.50"]},
            {"name": "region", "type": "VARCHAR", "sample_values": ["North", "South"]},
        ],
    }


@pytest.fixture
def sample_few_shots():
    return [
        {"question": "Total sales by region", "sql": "SELECT region, SUM(amount) FROM sales GROUP BY region;"},
        {"question": "Top products by revenue", "sql": "SELECT product, SUM(amount) FROM sales GROUP BY product ORDER BY SUM(amount) DESC;"},
        {"question": "Count of orders per month", "sql": "SELECT DATE_TRUNC('month', date) AS month, COUNT(*) FROM sales GROUP BY month;"},
    ]


@pytest.fixture(autouse=False)
def clean_cache():
    """Clear the in-memory SQL cache before each test."""
    import main as m
    m._cache.clear()
    yield
    m._cache.clear()
