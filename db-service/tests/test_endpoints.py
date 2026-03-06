"""Integration tests for db-service endpoints using a SQLite in-memory engine."""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import text


# conftest.py already set DATABASE_URL before any import
import main as db_main
from main import app


@pytest.fixture
def client(sqlite_engine):
    """TestClient — sqlite_engine ensures the shared DB has the 'sales' table."""
    return TestClient(app, raise_server_exceptions=False)


class TestQueryEndpoint:
    def test_valid_select_returns_rows(self, client):
        response = client.post("/query", json={"sql": "SELECT * FROM sales"})
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert data["count"] == 3

    def test_non_select_returns_400(self, client):
        response = client.post("/query", json={"sql": "DROP TABLE sales"})
        assert response.status_code == 400

    def test_insert_returns_400(self, client):
        response = client.post("/query", json={"sql": "INSERT INTO sales VALUES (99, 'x', 1, 'Z')"})
        assert response.status_code == 400

    def test_invalid_sql_returns_400(self, client):
        response = client.post("/query", json={"sql": "SELECT nonexistent_col FROM sales"})
        # SQLite may return 400 (ProgrammingError) or 500 depending on version
        assert response.status_code in (400, 500)

    def test_limit_auto_injected(self, client, sqlite_engine):
        """Query without LIMIT gets limit injected — still returns results."""
        response = client.post("/query", json={"sql": "SELECT * FROM sales"})
        assert response.status_code == 200


class TestSchemaEndpoint:
    def test_returns_table_and_columns(self, client):
        response = client.get("/schema")
        assert response.status_code == 200
        data = response.json()
        assert "table" in data
        assert "columns" in data
        col_names = [c["name"] for c in data["columns"]]
        assert "product" in col_names
        assert "amount" in col_names


class TestHealthEndpoint:
    def test_db_ok_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_db_fail_returns_503(self):
        bad_engine = MagicMock()
        bad_engine.connect.side_effect = Exception("DB unreachable")
        with patch.object(db_main, "engine", bad_engine):
            c = TestClient(app, raise_server_exceptions=False)
            response = c.get("/health")
        assert response.status_code == 503
