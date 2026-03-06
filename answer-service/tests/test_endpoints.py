"""Integration tests for answer-service endpoints."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


class TestAnswerEndpoint:
    def test_empty_rows_returns_fallback_without_ollama(self, client):
        with patch("main.httpx.AsyncClient") as mock_cls:
            response = client.post(
                "/answer",
                json={"question": "Total sales?", "sql": "SELECT SUM(amount)", "rows": []},
            )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "no" in data["answer"].lower() and "result" in data["answer"].lower()
        # Ollama should NOT be called for empty rows
        mock_cls.assert_not_called()

    def test_ollama_good_response_returned(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": "El total es 100."}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            response = client.post(
                "/answer",
                json={
                    "question": "Total?",
                    "sql": "SELECT SUM(amount) FROM sales",
                    "rows": [{"total": 100}],
                },
            )
        assert response.status_code == 200
        assert response.json()["answer"] == "El total es 100."

    def test_hallucinated_response_returns_fallback(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Invented number 99999 not in rows
        mock_resp.json.return_value = {"response": "El total es 99999 pesos."}

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            response = client.post(
                "/answer",
                json={
                    "question": "Total?",
                    "sql": "SELECT SUM(amount) FROM sales",
                    "rows": [{"total": 100}],
                },
            )
        assert response.status_code == 200
        # Should return fallback, not the hallucinated response
        assert "99999" not in response.json()["answer"]

    def test_ollama_error_returns_502(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("main.httpx.AsyncClient", return_value=mock_client):
            response = client.post(
                "/answer",
                json={
                    "question": "Total?",
                    "sql": "SELECT 1",
                    "rows": [{"total": 100}],
                },
            )
        assert response.status_code == 502
