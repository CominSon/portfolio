"""Тест lineage на реальной структуре p_ukp_weeks (temp _bb + UNION ALL)."""

import unittest
from pathlib import Path

from gp_mcp_agent.src.utils.sql_block_extractor import analyze_procedure_for_target

WORK = "s_grnplm_ld_blago_ubhq_work"
REAL_DDL_PATH = Path("/home/my_profile/Загрузки/new 3 (1).txt")


class PUkpWeeksLineageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not REAL_DDL_PATH.is_file():
            cls.sql = None
            return
        cls.sql = REAL_DDL_PATH.read_text(encoding="utf-8")
        # pg_get_functiondef format: body inside AS $$ ... $$
        if "AS $$" in cls.sql:
            start = cls.sql.index("AS $$") + len("AS $$")
            end = cls.sql.rindex("$$")
            cls.body = cls.sql[start:end]
        else:
            cls.body = cls.sql

    def setUp(self):
        if not self.sql:
            self.skipTest("файл эталонного DDL не найден")

    def test_reads_from_t_ukp_weeks_b(self):
        analysis = analyze_procedure_for_target(self.body, WORK, "t_ukp_weeks_b")
        data = set(analysis.get("data_reads_from") or [])
        refs = set(analysis.get("reference_reads_from") or [])

        self.assertIn("{0}.smd_dzo_days".format(WORK), data)
        self.assertIn("{0}.bpif_192368_oper2".format(WORK), data)
        self.assertIn("{0}.business_plan".format(WORK), refs)

        self.assertNotIn("f_get_fio", " ".join(data).lower())

        temp = analysis.get("temp_table_lineage") or []
        bb = [t for t in temp if t.get("temp") == "_bb"]
        self.assertTrue(bb)
        self.assertIn("{0}.smd_dzo_days".format(WORK), bb[0].get("physical_sources") or [])

        branches = analysis.get("union_branches") or []
        self.assertGreaterEqual(len(branches), 2)

    def test_reads_from_t_ukp_weeks_internal(self):
        """Внутри p_ukp_weeks есть второй INSERT — в t_ukp_weeks (не qs_*)."""
        analysis = analyze_procedure_for_target(self.body, WORK, "t_ukp_weeks")
        data = analysis.get("data_reads_from") or []
        self.assertEqual(data, ["{0}.t_ukp_weeks_b".format(WORK)])


if __name__ == "__main__":
    unittest.main()
