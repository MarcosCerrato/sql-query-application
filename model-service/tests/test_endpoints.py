"""Integration tests for model-service endpoints using AsyncMock."""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient

import service
import main
from main import app
from service import _cache


@pytest.fixture(autouse=True)
def clear_cache():
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture
def sample_schema():
    return {
        "table": "sales",
        "columns": [
            {"name": "id", "type": "INTEGER", "sample_values": ["1", "2"]},
            {"name": "product", "type": "VARCHAR", "sample_values": ["Widget"]},
            {"name": "amount", "type": "NUMERIC", "sample_values": ["100.00"]},
        ],
    }


@pytest.fixture
def sample_few_shots():
    return [
        {"question": "Total sales", "sql": "SELECT SUM(amount) FROM sales;"},
    ]


@pytest.fixture
def client(sample_schema, sample_few_shots):
    """TestClient with pre-seeded app state (no lifespan)."""
    app.state.schema = sample_schema
    app.state.few_shots = sample_few_shots
    # We'll inject a mock http_client per test
    return TestClient(app, raise_server_exceptions=False)


class TestTextToSql:
    def test_valid_ollama_response_returns_sql(self, client, sample_schema, sample_few_shots):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "SELECT * FROM sales"}
        mock_client.post = AsyncMock(return_value=mock_resp)

        app.state.http_client = mock_client

        response = client.post("/text-to-sql", json={"question": "Show all sales"})
        assert response.status_code == 200
        data = response.json()
        assert "sql" in data
        assert data["sql"].upper().startswith("SELECT")

    def test_cache_hit_skips_ollama(self, client, sample_schema):
        # Pre-seed cache
        from service import _cache_key, cache_set
        key = _cache_key("Show all sales", sample_schema)
        cache_set(key, "SELECT cached FROM sales;")

        mock_client = AsyncMock()
        mock_client.post = AsyncMock()  # should NOT be called
        app.state.http_client = mock_client

        response = client.post("/text-to-sql", json={"question": "Show all sales"})
        assert response.status_code == 200
        data = response.json()
        assert data["cached"] is True
        mock_client.post.assert_not_called()

    def test_ollama_returns_garbage_gives_422(self, client):
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": "I cannot help with that request."}
        mock_client.post = AsyncMock(return_value=mock_resp)
        app.state.http_client = mock_client

        response = client.post("/text-to-sql", json={"question": "something"})
        assert response.status_code == 422



class TestGenerateSqlRetry:
    """Test the retry logic in generate_sql."""

    @pytest.mark.asyncio
    async def test_first_fail_second_success(self, sample_schema, sample_few_shots):
        call_count = 0

        async def fake_ollama(client, prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "Not a SQL query"
            return "SELECT * FROM sales"

        with patch("service.call_ollama", side_effect=fake_ollama):
            import httpx
            async with httpx.AsyncClient() as c:
                result = await service.generate_sql(c, "q", sample_schema, sample_few_shots)
        assert result.upper().startswith("SELECT")
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_three_failures_raises_422(self, sample_schema, sample_few_shots):
        from fastapi import HTTPException

        async def always_bad(client, prompt):
            return "I cannot do that."

        with patch("service.call_ollama", side_effect=always_bad):
            import httpx
            with pytest.raises(HTTPException) as exc_info:
                async with httpx.AsyncClient() as c:
                    await service.generate_sql(c, "q", sample_schema, sample_few_shots)
        assert exc_info.value.status_code == 422
