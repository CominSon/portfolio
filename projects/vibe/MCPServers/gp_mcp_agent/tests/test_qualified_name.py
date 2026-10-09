import unittest

from gp_mcp_agent.src.utils.qualified_name import parse_schema_object, resolve_schema_name


class TestQualifiedName(unittest.TestCase):
    def test_parse_logs_procedure(self):
        schema, table = parse_schema_object(
            "s_grnplm_ld_blago_ubhq_in.logs_procedure"
        )
        self.assertEqual(schema, "s_grnplm_ld_blago_ubhq_in")
        self.assertEqual(table, "logs_procedure")

    def test_resolve_schema_only_field(self):
        schema, name = resolve_schema_name({
            "schema": "s_grnplm_ld_blago_ubhq_in.logs_procedure",
            "name": "",
        }, name_key="table")
        self.assertEqual(schema, "s_grnplm_ld_blago_ubhq_in")
        self.assertEqual(name, "logs_procedure")

    def test_qualified_param(self):
        schema, name = resolve_schema_name({
            "qualified": "s_grnplm_ld_blago_ubhq_in.pxf_truncate_and_insert",
        })
        self.assertEqual(schema, "s_grnplm_ld_blago_ubhq_in")
        self.assertEqual(name, "pxf_truncate_and_insert")


if __name__ == "__main__":
    unittest.main()
