"""Тесты классификации reads_from."""

import unittest

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.utils.read_classifier import is_reference_source, partition_reads
from gp_mcp_agent.src.utils.sql_block_extractor import analyze_procedure_for_target


class ReadClassifierTest(unittest.TestCase):
    def test_reference_sources(self):
        work = settings.GP_ALLOWED_SCHEMAS[2]
        self.assertTrue(is_reference_source("{0}.f_get_fio_qlik".format(work)))
        self.assertTrue(is_reference_source("{0}.business_plan".format(work)))
        self.assertFalse(is_reference_source("{0}.bpif_192368_oper2".format(work)))

    def test_cte_driving_vs_joins(self):
        work = settings.GP_ALLOWED_SCHEMAS[2]
        sql = """
        WITH s AS (
            SELECT x FROM {work}.t_base t
            JOIN {work}.business_plan b ON 1=1
        )
        INSERT INTO {work}.t_ukp_weeks_b SELECT x FROM s;
        """.format(work=work)
        analysis = analyze_procedure_for_target(sql, work, "t_ukp_weeks_b")
        self.assertEqual(
            analysis.get("data_reads_from"),
            ["{0}.t_base".format(work)],
        )
        refs = analysis.get("reference_reads_from") or []
        refs = analysis.get("reference_reads_from") or []
        self.assertIn("{0}.business_plan".format(work), refs)

    def test_partition_reads(self):
        data, refs = partition_reads([
            "work.a",
            "work.business_plan",
            "work.f_x",
            "s_grnplm_ld_blago_ubhq_ext.ft_client_aggr_mnth",
        ])
        self.assertEqual(data, ["work.a"])
        self.assertIn("work.business_plan", refs)
        self.assertIn("work.f_x", refs)
        self.assertIn("s_grnplm_ld_blago_ubhq_ext.ft_client_aggr_mnth", refs)


if __name__ == "__main__":
    unittest.main()
