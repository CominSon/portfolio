"""Тесты нормализации DDL."""

import unittest

from mcp_workspace_config.text_normalize import (
    ddl_looks_corrupted,
    decode_json_escaped_text,
    normalize_line_endings,
)


class TextNormalizeTest(unittest.TestCase):
    def test_decode_literal_newlines(self):
        raw = "SELECT 1;\\n\\t\\n\\tFROM t;"
        out = normalize_line_endings(raw)
        self.assertIn("\n", out)
        self.assertNotIn("\\n\\t", out)

    def test_corrupted_ddl_detected(self):
        bad = "FROM work.smd_dzo_days as d ;\\n\\t\\n\\t\\n\\t"
        self.assertTrue(ddl_looks_corrupted(bad))


if __name__ == "__main__":
    unittest.main()
