import unittest

from gp_mcp_agent.src.utils.sql_table_refs import extract_table_refs, format_table_refs


VIEW_BODY = """
 SELECT x.col
 FROM prx_fin_mis3_s_grnplm_as_fin_mis3_misplt_1b4.v_is0540_bo_je_details_h_18764734_view;
"""


class SqlTableRefsTest(unittest.TestCase):
    def test_view_external_schema_included_when_all(self):
        refs = extract_table_refs(VIEW_BODY, include_all_schemas=True)
        self.assertEqual(len(refs), 1)
        self.assertIn("prx_fin", refs[0][0].lower())

    def test_view_external_excluded_by_default(self):
        refs = extract_table_refs(VIEW_BODY, include_all_schemas=False)
        self.assertEqual(refs, [])

    def test_format_marks_external(self):
        refs = extract_table_refs(VIEW_BODY, include_all_schemas=True)
        formatted = format_table_refs(refs)
        self.assertTrue(formatted[0]["is_external"])
        self.assertIn("prx_fin", formatted[0]["qualified"])


if __name__ == "__main__":
    unittest.main()
