"""Tests for pure functions in model-service (no external calls)."""
import time
from unittest.mock import patch

import pytest

from service import (
    _cache_key,
    build_prompt,
    cache_get,
    cache_set,
    extract_sql,
    format_schema,
    looks_like_sql,
    select_few_shots,
    _cache,
)


# ── extract_sql ────────────────────────────────────────────────────────────────

class TestExtractSql:
    def test_no_fences_returns_as_is(self):
        result = extract_sql("SELECT * FROM sales")
        assert result == "SELECT * FROM sales;"

    def test_sql_fence_extracted(self):
        result = extract_sql("```sql\nSELECT * FROM sales\n```")
        assert "SELECT * FROM sales" in result
        assert "```" not in result

    def test_generic_fence_extracted(self):
        result = extract_sql("```\nSELECT id FROM sales\n```")
        assert "SELECT id FROM sales" in result
        assert "```" not in result

    def test_trailing_semicolon_normalized(self):
        result = extract_sql("SELECT * FROM sales;")
        assert result.endswith(";")
        # Only one semicolon at end
        assert result.count(";") == 1

    def test_empty_string(self):
        result = extract_sql("")
        assert result == ";"

    def test_adds_semicolon_if_missing(self):
        result = extract_sql("SELECT 1")
        assert result.endswith(";")


# ── looks_like_sql ─────────────────────────────────────────────────────────────

class TestLooksLikeSql:
    def test_select_returns_true(self):
        assert looks_like_sql("SELECT * FROM sales") is True

    def test_with_returns_true(self):
        assert looks_like_sql("WITH cte AS (SELECT 1) SELECT * FROM cte") is True

    def test_plain_text_returns_false(self):
        assert looks_like_sql("Sure, here is the query you asked for") is False

    def test_case_insensitive_select(self):
        assert looks_like_sql("select id from sales") is True

    def test_case_insensitive_with(self):
        assert looks_like_sql("with cte as (select 1) select * from cte") is True

    def test_empty_string_returns_false(self):
        assert looks_like_sql("") is False

    def test_leading_whitespace(self):
        assert looks_like_sql("   SELECT 1") is True


# ── select_few_shots ───────────────────────────────────────────────────────────

class TestSelectFewShots:
    def test_keyword_match_returns_relevant(self, sample_few_shots):
        result = select_few_shots("total sales by region", sample_few_shots, n=1)
        assert len(result) == 1
        assert "region" in result[0]["question"].lower()

    def test_n_larger_than_list_returns_all(self, sample_few_shots):
        result = select_few_shots("anything", sample_few_shots, n=100)
        assert len(result) == len(sample_few_shots)

    def test_empty_shots_returns_empty(self):
        result = select_few_shots("some question", [], n=3)
        assert result == []

    def test_returns_at_most_n(self, sample_few_shots):
        result = select_few_shots("sales region products", sample_few_shots, n=2)
        assert len(result) <= 2


# ── format_schema ──────────────────────────────────────────────────────────────

class TestFormatSchema:
    def test_includes_sample_values(self, sample_schema):
        result = format_schema(sample_schema)
        assert "Widget" in result
        assert "North" in result

    def test_includes_column_names(self, sample_schema):
        result = format_schema(sample_schema)
        assert "product" in result
        assert "amount" in result

    def test_no_sample_values_omits_them(self):
        schema = {
            "table": "sales",
            "columns": [{"name": "id", "type": "INTEGER"}],
        }
        result = format_schema(schema)
        assert "id" in result
        assert "INTEGER" in result
        # No colon-separated sample values
        assert ": " not in result

    def test_empty_columns(self):
        result = format_schema({"table": "sales", "columns": []})
        assert result == ""


# ── build_prompt ───────────────────────────────────────────────────────────────

class TestBuildPrompt:
    def test_no_error_context_excludes_error_section(self, sample_schema, sample_few_shots):
        prompt = build_prompt("How many sales?", sample_schema, sample_few_shots)
        assert "Previous attempt failed" not in prompt

    def test_with_error_context_includes_it(self, sample_schema, sample_few_shots):
        prompt = build_prompt(
            "How many sales?", sample_schema, sample_few_shots,
            error_context="column does not exist"
        )
        assert "column does not exist" in prompt

    def test_few_shots_appear_in_output(self, sample_schema, sample_few_shots):
        prompt = build_prompt("Top regions", sample_schema, sample_few_shots[:1])
        assert sample_few_shots[0]["sql"] in prompt

    def test_question_appears_in_output(self, sample_schema, sample_few_shots):
        question = "What is the total revenue?"
        prompt = build_prompt(question, sample_schema, sample_few_shots)
        assert question in prompt

    def test_table_name_appears(self, sample_schema, sample_few_shots):
        prompt = build_prompt("query", sample_schema, sample_few_shots)
        assert "sales" in prompt


# ── _cache_key ─────────────────────────────────────────────────────────────────

class TestCacheKey:
    def test_same_inputs_same_hash(self, sample_schema):
        k1 = _cache_key("question", sample_schema)
        k2 = _cache_key("question", sample_schema)
        assert k1 == k2

    def test_different_questions_different_hash(self, sample_schema):
        k1 = _cache_key("question one", sample_schema)
        k2 = _cache_key("question two", sample_schema)
        assert k1 != k2

    def test_returns_64_char_string(self, sample_schema):
        key = _cache_key("test", sample_schema)
        assert isinstance(key, str)
        assert len(key) == 64


# ── cache_get / cache_set ──────────────────────────────────────────────────────

class TestCache:
    def setup_method(self):
        _cache.clear()

    def teardown_method(self):
        _cache.clear()

    def test_set_then_get_returns_value(self):
        cache_set("key1", "SELECT 1;")
        assert cache_get("key1") == "SELECT 1;"

    def test_missing_key_returns_none(self):
        assert cache_get("nonexistent_key") is None

    def test_expired_entry_returns_none(self):
        cache_set("key2", "SELECT 2;")
        # Fake that the entry was set 400 seconds ago (TTL is 300)
        _cache["key2"] = (time.time() - 400, "SELECT 2;")
        assert cache_get("key2") is None

    def test_expired_entry_is_removed(self):
        cache_set("key3", "SELECT 3;")
        _cache["key3"] = (time.time() - 400, "SELECT 3;")
        cache_get("key3")
        assert "key3" not in _cache
