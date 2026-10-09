"""Регресс: fetch_iter не должен читать named cursor после закрытия транзакции."""

import unittest
from unittest.mock import MagicMock, patch

from gp_mcp_agent.src.db import db_manager


class FakeRow(object):
    def __init__(self, mapping):
        self._mapping = mapping


class TestFetchIterCursorLifetime(unittest.TestCase):
    def test_fetchmany_runs_inside_begin_context(self):
        rows = [FakeRow({"a": 1}), FakeRow({"a": 2})]
        result = MagicMock()
        result.fetchmany.side_effect = [rows, []]

        conn = MagicMock()
        conn.execution_options.return_value = conn
        conn.execute.return_value = result

        begin_cm = MagicMock()
        begin_cm.__enter__.return_value = conn
        begin_cm.__exit__.return_value = False

        engine = MagicMock()
        engine.begin.return_value = begin_cm

        closed = {"exited": False}

        def on_exit(*_a, **_k):
            closed["exited"] = True
            return False

        begin_cm.__exit__.side_effect = on_exit

        batches = [rows, []]

        def fetchmany(_size):
            if closed["exited"]:
                raise Exception("named cursor isn't valid anymore")
            return batches.pop(0)

        result.fetchmany.side_effect = fetchmany

        with patch.object(db_manager, "get_engine", return_value=engine):
            with patch.object(db_manager, "_apply_session_settings"):
                with patch.object(db_manager, "_sql_text", side_effect=lambda s: s):
                    out = list(db_manager.fetch_iter("SELECT 1", batch_size=10))

        self.assertEqual(out, [{"a": 1}, {"a": 2}])
        self.assertTrue(closed["exited"])
        begin_cm.__enter__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
