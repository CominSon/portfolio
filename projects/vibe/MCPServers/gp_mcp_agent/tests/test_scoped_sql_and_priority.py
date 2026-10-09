"""Тесты scoped SQL и приоритета writers."""

import unittest

from gp_mcp_agent.resources import settings
from gp_mcp_agent.src.utils.sql_block_extractor import (
    analyze_procedure_for_target,
    extract_driving_reads_for_target,
    extract_scoped_reads_for_target,
)
from gp_mcp_agent.src.utils.write_classifier import (
    branch_role_for_target,
    pick_suggested_writer,
    rank_writers,
)


class ScopedSqlTest(unittest.TestCase):
    def test_scoped_reads_only_target_block(self):
        in_sch = settings.GP_MATERIALIZED_SCHEMA
        work_sch = settings.GP_ALLOWED_SCHEMAS[2]
        sql = """
        INSERT INTO {work}.smd_dzo_days
        SELECT a, b FROM {in_s}.smd_dzo_days t;
        INSERT INTO {work}.other_table SELECT 1;
        UPDATE {work}.smd_dzo_days SET x=1;
        """.format(work=work_sch, in_s=in_sch)
        scoped, _ = extract_scoped_reads_for_target(sql, work_sch, "smd_dzo_days")
        qualified = [r["qualified"] for r in scoped]
        self.assertIn("{0}.smd_dzo_days".format(in_sch), qualified)
        self.assertNotIn("{0}.other_table".format(work_sch), qualified)

    def test_cte_driving_table_only_not_joins(self):
        """Модель p_ukp_weeks: CTE с driving-таблицей + JOIN внутри CTE; снаружи только CTE."""
        work_sch = settings.GP_ALLOWED_SCHEMAS[2]
        sql = """
        WITH ukp_src AS (
            SELECT t.client_id, t.amt, o.bpif_val, b.plan_amt
            FROM {work}.t_ukp_weeks_src t
            JOIN {work}.bpif_192368_oper2 o ON o.id = t.client_id
            JOIN {work}.business_plan b ON b.id = o.plan_id
            LEFT JOIN {work}.f_get_fio_qlik() f ON true
        )
        INSERT INTO {work}.t_ukp_weeks_b
        SELECT client_id, amt, bpif_val, plan_amt FROM ukp_src;
        """.format(work=work_sch)
        analysis = analyze_procedure_for_target(sql, work_sch, "t_ukp_weeks_b")
        data = analysis.get("data_reads_from") or []
        joins = analysis.get("join_reads_in_query") or []
        refs = analysis.get("reference_reads_from") or []
        self.assertEqual(data, ["{0}.t_ukp_weeks_src".format(work_sch)])
        self.assertIn("{0}.bpif_192368_oper2".format(work_sch), joins)
        self.assertIn("{0}.business_plan".format(work_sch), refs)
        self.assertTrue(any("f_get_fio" in r for r in refs))

    def test_cte_driving_direct_from(self):
        work_sch = settings.GP_ALLOWED_SCHEMAS[2]
        in_sch = settings.GP_MATERIALIZED_SCHEMA
        sql = """
        WITH agg AS (
            SELECT client_id, sum_amt
            FROM {in_s}.smd_ft_client_aggr_mnth
            GROUP BY 1, 2
        )
        INSERT INTO {work}.t_ukp_weeks_b
        SELECT a.client_id FROM agg a;
        """.format(work=work_sch, in_s=in_sch)
        driving, used_cte, _, _ = extract_driving_reads_for_target(
            sql, work_sch, "t_ukp_weeks_b"
        )[:4]
        qualified = [r["qualified"] for r in driving]
        self.assertTrue(used_cte)
        self.assertEqual(qualified, ["{0}.smd_ft_client_aggr_mnth".format(in_sch)])


class WriterPriorityTest(unittest.TestCase):
    def test_insert_primary_over_update(self):
        insert_w = {
            "qualified": "work.p_create",
            "write_roles": ["insert"],
            "branch_role": branch_role_for_target(["insert"]),
        }
        update_w = {
            "qualified": "work.p_dzo_days",
            "write_roles": ["update"],
            "branch_role": branch_role_for_target(["update"]),
        }
        self.assertEqual(pick_suggested_writer([update_w, insert_w])["qualified"], "work.p_create")
        ranked = rank_writers([update_w, insert_w])
        self.assertEqual(ranked[0]["qualified"], "work.p_create")


if __name__ == "__main__":
    unittest.main()
