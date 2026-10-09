"""Тесты классификации DML-процедур."""

import unittest

from gp_mcp_agent.src.utils.write_classifier import (
    classify_write_to_table,
    is_excluded_by_suffix,
    pick_suggested_writer,
    write_roles_summary,
)


class WriteClassifierTest(unittest.TestCase):
    def test_truncate_insert(self):
        sql = """
        TRUNCATE TABLE work.qs_t_ukp_weeks;
        INSERT INTO work.qs_t_ukp_weeks SELECT * FROM work.t_ukp_weeks_b;
        """
        roles = classify_write_to_table(sql, "work", "qs_t_ukp_weeks")
        self.assertIn("truncate_insert", roles)

    def test_insert_only(self):
        sql = "INSERT INTO work.t_foo SELECT 1;"
        self.assertEqual(classify_write_to_table(sql, "work", "t_foo"), ["insert"])

    def test_update(self):
        sql = "UPDATE work.t_foo SET col = 1 WHERE id > 0;"
        self.assertEqual(classify_write_to_table(sql, "work", "t_foo"), ["update"])

    def test_reference_only(self):
        sql = "SELECT * FROM work.t_foo JOIN work.t_bar ON 1=1;"
        self.assertEqual(classify_write_to_table(sql, "work", "t_foo"), [])

    def test_suffix_filter_opt_in(self):
        self.assertFalse(is_excluded_by_suffix("p_load_foo_dtl", None))
        self.assertFalse(is_excluded_by_suffix("p_load_foo_dtl", []))
        self.assertTrue(is_excluded_by_suffix("p_load_foo_dtl", ["_dtl"]))
        self.assertFalse(is_excluded_by_suffix("p_load_foo", ["_dtl"]))

    def test_pick_suggested_prefers_insert(self):
        candidates = [
            {"qualified": "work.p_b", "write_roles": ["insert"], "branch_role": "primary"},
            {"qualified": "work.p_a", "write_roles": ["update"], "branch_role": "supplement"},
        ]
        self.assertEqual(pick_suggested_writer(candidates)["qualified"], "work.p_b")

    def test_roles_summary(self):
        self.assertEqual(write_roles_summary(["update"]), "update")


if __name__ == "__main__":
    unittest.main()
