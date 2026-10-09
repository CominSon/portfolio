"""compact get_function не должен выкидывать data_reads_from."""

import unittest

from mcp_workspace_config.response_compact import compact_tool_result, _json_size


class CompactFunctionLineageTest(unittest.TestCase):
    def test_preserves_reads_when_oversized(self):
        result = {
            "mode": "lineage",
            "procedure": "work.p_ukp_weeks",
            "writes_to": "work.t_ukp_weeks_b",
            "write_role": "truncate_insert",
            "branch_role": "primary",
            "data_reads_from": ["work.bpif_192368_oper2", "work.smd_dzo_days"],
            "reads_from_for_lineage": ["work.bpif_192368_oper2", "work.smd_dzo_days"],
            "reference_reads_from": ["work.business_plan"],
            "suggested_reads_from": ["work.bpif_192368_oper2", "work.smd_dzo_days"],
            "dml_block_previews": ["x" * 8000, "y" * 8000],
            "cte_chain": [{"cte": "c", "preview": "z" * 3000} for _ in range(20)],
            "union_branches": [{"branch_preview": "w" * 2000, "sources": ["a"]} for _ in range(10)],
            "temp_table_lineage": [{"temp": "_bb", "physical_sources": ["work.smd_dzo_days"]}],
        }
        self.assertGreater(_json_size(result), 5000)
        out = compact_tool_result("get_function", result, server="gp")
        self.assertEqual(
            out.get("data_reads_from") or out.get("reads_from_for_lineage"),
            ["work.bpif_192368_oper2", "work.smd_dzo_days"],
        )
        self.assertNotIn("truncated", out) or out.get("data_reads_from")
        self.assertFalse(out.get("summary") is not None and "data_reads_from" not in out)


if __name__ == "__main__":
    unittest.main()
