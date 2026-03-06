"""Tests for pure functions in answer-service (no HTTP calls)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import build_prompt, fallback_answer, looks_hallucinated


class TestFallbackAnswer:
    def test_empty_rows_says_no_results(self):
        result = fallback_answer("How many sales?", [])
        assert "no" in result.lower() and "result" in result.lower()

    def test_single_row_says_el_resultado(self):
        rows = [{"product": "Widget", "amount": 100}]
        result = fallback_answer("Top product?", rows)
        assert "result" in result.lower()

    def test_multiple_rows_says_principales_resultados(self):
        rows = [
            {"product": "Widget", "amount": 100},
            {"product": "Gadget", "amount": 250},
            {"product": "Doohickey", "amount": 75},
        ]
        result = fallback_answer("Top products?", rows)
        assert "result" in result.lower()

    def test_truncates_to_top_3(self):
        rows = [{"product": f"P{i}", "amount": i * 10} for i in range(10)]
        result = fallback_answer("Products?", rows)
        # Should only include first 3 products
        assert "P9" not in result  # 10th product should be truncated
        assert "P0" in result

    def test_single_row_contains_values(self):
        rows = [{"amount": 999}]
        result = fallback_answer("Total?", rows)
        assert "999" in result


class TestLooksHallucinated:
    def test_number_present_in_rows_returns_false(self):
        rows = [{"total": 12345}]
        text = "El total es 12345 unidades."
        assert looks_hallucinated(text, rows) is False

    def test_invented_number_returns_true(self):
        rows = [{"total": 100}]
        text = "El total es 99999 unidades."
        assert looks_hallucinated(text, rows) is True

    def test_no_4digit_numbers_in_response_returns_false(self):
        rows = [{"product": "Widget"}]
        text = "El producto más vendido es Widget."
        assert looks_hallucinated(text, rows) is False

    def test_number_in_rows_as_string_not_hallucinated(self):
        rows = [{"year": "2023"}]
        text = "Las ventas en 2023 fueron las más altas."
        assert looks_hallucinated(text, rows) is False


class TestBuildPrompt:
    def test_rows_truncated_to_5(self):
        rows = [{"id": i} for i in range(10)]
        prompt = build_prompt("question", "SELECT 1", rows)
        # Only first 5 rows should appear
        import json
        truncated = json.loads(prompt.split("Data: ")[1].split("\n")[0])
        assert len(truncated) == 5

    def test_sql_appears_in_prompt(self):
        rows = [{"x": 1}]
        sql = "SELECT x FROM t"
        prompt = build_prompt("question", sql, rows)
        assert sql in prompt

    def test_question_appears_in_prompt(self):
        rows = [{"x": 1}]
        question = "What is the top product?"
        prompt = build_prompt(question, "SELECT 1", rows)
        assert question in prompt
