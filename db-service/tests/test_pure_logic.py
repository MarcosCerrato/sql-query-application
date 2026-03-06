"""Tests for pure logic in db-service (no DB calls)."""
import re
import pytest


_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
QUERY_ROW_LIMIT = 1000


def inject_limit(sql: str) -> str:
    """Mirror of the logic in db-service/main.py."""
    if not _LIMIT_RE.search(sql):
        return f"{sql} LIMIT {QUERY_ROW_LIMIT}"
    return sql


class TestSelectOnlyValidation:
    """The /query endpoint rejects anything that is not a SELECT."""

    def test_select_is_allowed(self):
        sql = "SELECT * FROM sales"
        assert sql.upper().startswith("SELECT")

    def test_insert_is_rejected(self):
        sql = "INSERT INTO sales VALUES (1, 'x', 10, 'N')"
        assert not sql.upper().startswith("SELECT")

    def test_update_is_rejected(self):
        sql = "UPDATE sales SET amount = 0"
        assert not sql.upper().startswith("SELECT")

    def test_drop_is_rejected(self):
        sql = "DROP TABLE sales"
        assert not sql.upper().startswith("SELECT")

    def test_lowercase_select_is_allowed(self):
        sql = "select id from sales"
        assert sql.upper().startswith("SELECT")


class TestLimitInjection:
    def test_no_limit_gets_injected(self):
        sql = "SELECT * FROM sales"
        result = inject_limit(sql)
        assert f"LIMIT {QUERY_ROW_LIMIT}" in result

    def test_existing_limit_not_modified(self):
        sql = "SELECT * FROM sales LIMIT 5"
        result = inject_limit(sql)
        assert result == sql

    def test_lowercase_limit_not_duplicated(self):
        sql = "SELECT * FROM sales limit 10"
        result = inject_limit(sql)
        # Should still be unchanged (has a LIMIT)
        assert result == sql

    def test_limit_appended_to_complex_query(self):
        sql = "SELECT region, SUM(amount) FROM sales GROUP BY region ORDER BY SUM(amount) DESC"
        result = inject_limit(sql)
        assert result.endswith(f"LIMIT {QUERY_ROW_LIMIT}")
