"""Tests for pure functions in answer-service (no HTTP calls)."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from service import build_prompt


class TestBuildPrompt:
    def test_rows_truncated_to_20(self):
        rows = [{"id": i} for i in range(25)]
        prompt = build_prompt("question", "SELECT 1", rows)
        import json
        truncated = json.loads(prompt.split("Data: ")[1].split("\n")[0])
        assert len(truncated) == 20

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
