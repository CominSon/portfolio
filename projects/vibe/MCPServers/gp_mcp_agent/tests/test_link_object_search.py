"""Тесты link_object_search."""

import unittest
from unittest.mock import patch

from gp_mcp_agent.src.utils.link_object_search import (
    merge_writer_lists,
    search_patterns_for_table,
)
from gp_mcp_agent.src.utils.write_classifier import rank_writers


class LinkObjectSearchTest(unittest.TestCase):
    def test_search_patterns(self):
        pats = search_patterns_for_table("s_grnplm_ld_blago_ubhq_work", "smd_dzo_days")
        self.assertIn("smd_dzo_days", pats)
        self.assertIn("s_grnplm_ld_blago_ubhq_work.smd_dzo_days", pats)

    def test_merge_prefers_primary(self):
        a = [{
            "qualified": "w.p_upd",
            "write_roles": ["update"],
            "write_role": "update",
            "branch_role": "supplement",
            "discovery": "catalog",
        }]
        b = [{
            "qualified": "w.p_load",
            "write_roles": ["insert"],
            "write_role": "insert",
            "branch_role": "primary",
            "discovery": "link_object",
        }]
        merged = merge_writer_lists(a, b)
        self.assertEqual(merged[0]["qualified"], "w.p_load")

    def test_discover_large_body_truncate_insert(self):
        from gp_mcp_agent.src.utils.link_object_search import discover_writers_via_link_object

        padding = "x" * 15000
        body = (
            padding
            + "\n truncate table w.tbl;\n insert into w.tbl select 1;\n"
        )
        refs = [{"schemaname": "w", "proname": "p_load", "kind": "function"}]

        with patch(
            "gp_mcp_agent.src.utils.link_object_search.find_referencing_objects",
            return_value=refs,
        ):
            with patch(
                "gp_mcp_agent.src.utils.link_object_search._fetch_function_body",
                return_value=body,
            ):
                writers = discover_writers_via_link_object("w", "tbl")
        self.assertEqual(len(writers), 1)
        self.assertIn("truncate", writers[0]["write_role"])
        from gp_mcp_agent.src.utils.link_object_search import discover_writers_via_link_object

        refs = [
            {"schemaname": "w", "proname": "p_read_only", "kind": "function"},
            {"schemaname": "w", "proname": "p_load", "kind": "function"},
        ]

        def fake_body(schema, name):
            if name == "p_load":
                return "INSERT INTO w.tbl SELECT 1"
            return "SELECT * FROM w.tbl"

        with patch(
            "gp_mcp_agent.src.utils.link_object_search.find_referencing_objects",
            return_value=refs,
        ):
            with patch(
                "gp_mcp_agent.src.utils.link_object_search._fetch_function_body",
                side_effect=fake_body,
            ):
                writers = discover_writers_via_link_object("w", "tbl")
        self.assertEqual(len(writers), 1)
        self.assertEqual(writers[0]["qualified"], "w.p_load")


if __name__ == "__main__":
    unittest.main()
