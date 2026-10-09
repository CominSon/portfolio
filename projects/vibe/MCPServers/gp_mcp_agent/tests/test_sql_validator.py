"""Тесты SQL-валидатора."""

import unittest

from gp_mcp_agent.src.utils.sql_validator import validate_sql


class TestSqlValidator(unittest.TestCase):
    def test_select_ok(self):
        validate_sql("SELECT 1")

    def test_with_ok(self):
        validate_sql("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_explain_ok(self):
        validate_sql("EXPLAIN SELECT 1")

    def test_insert_forbidden(self):
        with self.assertRaises(ValueError):
            validate_sql("INSERT INTO t VALUES (1)")

    def test_delete_in_comment_still_blocked(self):
        with self.assertRaises(ValueError):
            validate_sql("SELECT 1; DELETE FROM t")

    def test_drop_forbidden(self):
        with self.assertRaises(ValueError):
            validate_sql("DROP TABLE t")

    def test_comment_stripped_before_check(self):
        # Комментарии удаляются — важно не прятать реальный SQL в комментариях вручную
        validate_sql("SELECT 1 /* not a real statement */")


if __name__ == "__main__":
    unittest.main()
