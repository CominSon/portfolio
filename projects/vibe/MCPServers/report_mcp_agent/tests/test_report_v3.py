"""Тесты report-project v3.1."""

import tempfile
import unittest
from pathlib import Path

from report_mcp_agent.src.report import (
    context,
    docs_render,
    lineage_store,
    manifest,
    pxf_rules,
    revisions,
    scaffold,
    validators,
)
from report_mcp_agent.src.server.tool_registry import ToolRegistry


class ReportV31Test(unittest.TestCase):
    def test_pxf_name_exact(self):
        self.assertEqual(
            pxf_rules.pxf_lookup_name(
                "s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h"
            ),
            "is0540_bo_je_details_h",
        )
        self.assertNotEqual(pxf_rules.pxf_lookup_name("smd_is0540_bo_je_details_h"), "T_FCT_JE_DETAILS_H")

    def test_smd_on_in_is_pxf_work_is_intermediate(self):
        work_smd = "s_grnplm_ld_blago_ubhq_work.smd_is0540_bo_je_details_h"
        in_smd = "s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h"
        self.assertFalse(pxf_rules.is_pxf_source_candidate(work_smd))
        self.assertTrue(pxf_rules.is_pxf_source_candidate(in_smd))
        self.assertEqual(pxf_rules.classify_smd_object(work_smd)["role"], "intermediate")
        self.assertEqual(pxf_rules.classify_smd_object(in_smd)["role"], "pxf_candidate")
        self.assertIsNone(pxf_rules.validate_smd_placement(work_smd))
        self.assertIsNone(pxf_rules.validate_smd_placement(in_smd))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            scaffold.scaffold_project(root, "T", "s_grnplm_ld_blago_ubhq_work", "qs_t")
            # work.smd_* допустим как промежуточная — не ValueError
            lineage_store.upsert_lineage_step(
                root,
                procedure="work.p_x",
                writes_to="work.qs_t",
                reads_from=["s_grnplm_ld_blago_ubhq_work.smd_foo"],
            )
            ctx = context.build_context(root)
            self.assertFalse(
                any(
                    g.get("object") == "s_grnplm_ld_blago_ubhq_work.smd_foo"
                    and g.get("code") == "smd_source_unclassified"
                    for g in ctx["gaps"]
                )
            )
            self.assertFalse(
                any(h.get("object") == "s_grnplm_ld_blago_ubhq_work.smd_foo"
                    for h in ctx.get("smd_pxf_checklist") or [])
            )

    def test_object_slug_and_layout_dirs(self):
        from report_mcp_agent.src.report.naming import object_slug_from_table
        from report_mcp_agent.src.report import path_resolve

        self.assertEqual(object_slug_from_table("qs_t_ukp_weeks"), "ukp_weeks")
        args = {
            "report_title": "УКП Недельный",
            "final_table": "qs_t_ukp_weeks",
            "parent_path": "/tmp/reports_test_parent",
        }
        # не создаём — только путь
        p = path_resolve.resolve_new_project_path(args, cwd="/tmp")
        self.assertTrue(str(p).endswith("УКП Недельный/ukp_weeks") or str(p).replace("\\", "/").endswith("УКП Недельный/ukp_weeks"))

    def test_scaffold_manifest_in_registry_and_root_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "УКП Недельный"
            root = report / "ukp_weeks"
            out = scaffold.scaffold_project(
                root, "УКП Недельный", "s_grnplm_ld_blago_ubhq_work", "qs_t_ukp_weeks"
            )
            self.assertTrue(out["ok"])
            self.assertTrue((root / "agent_registry" / "REPORT_MANIFEST.json").is_file())
            self.assertFalse((root / "REPORT_MANIFEST.json").is_file())
            self.assertTrue((root / "README.md").is_file())
            self.assertTrue((root / "python" / "sync_all_ddl.py").is_file())
            self.assertTrue((root / "sql" / "ddl" / "objects" / "sources").is_dir())
            self.assertTrue((root / "sql" / "ddl" / "objects" / "intermediate").is_dir())
            self.assertTrue((root / "sql" / "ddl" / "objects" / "final").is_dir())
            self.assertEqual(out.get("object_folder"), "ukp_weeks")

            lineage_store.upsert_lineage_step(
                root,
                procedure="work.p_ukp",
                writes_to="work.qs_t_ukp_weeks",
                reads_from=["s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h"],
            )
            lineage_store.upsert_schedule_entry(
                root,
                kind="pxf",
                object_name="s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h",
                target="s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h",
                last_success="2026-10-01 06:00",
                pxf_table_name="is0540_bo_je_details_h",
            )
            rendered = docs_render.render_all(root, overwrite_business=True)
            self.assertTrue((root / "docs" / "lineage.svg").is_file())
            tech = (root / "docs" / "TECHNICAL.md").read_text(encoding="utf-8")
            self.assertIn("## 5. Порядок запуска", tech)
            self.assertIn("is0540_bo_je_details_h", tech)
            self.assertNotIn("Целевая таблица", tech)
            self.assertIn("## 4. Источники", tech)
            self.assertNotIn("Терминальн", tech)
            self.assertIn("lineage.svg", tech)
            biz = (root / "docs" / "BUSINESS.md").read_text(encoding="utf-8")
            self.assertIn("Поле", biz)
            self.assertIn("## 3. Источники", biz)
            self.assertIn("## 4. Промежуточные витрины", biz)

            from report_mcp_agent.src.report import files

            files.write_project_file(
                root, "sql/ddl/objects/work.qs_t_ukp_weeks.sql", "CREATE TABLE t();\n", True
            )
            files.write_project_file(
                root, "sql/ddl/functions/work.p_ukp.sql", "CREATE FUNCTION f() RETURNS void AS $$ $$;\n", True
            )
            ctx = context.build_context(root)
            self.assertFalse(
                any(
                    g.get("object") == "s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h"
                    and g.get("code") == "smd_source_unclassified"
                    for g in ctx["gaps"]
                )
            )
            v = validators.validate_project(root)
            self.assertTrue(v["ok"], v)

    def test_revision_cascade_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "p"
            scaffold.scaffold_project(root, "T", "work", "t1")
            rev = revisions.add_revision(root, "добавь p_copy")
            self.assertEqual(rev["open_count"], 1)
            names = {t["name"] for t in ToolRegistry().list_tools()}
            self.assertIn("upsert_schedule_entry", names)
            self.assertIn("refresh_project_ddl", names)
            self.assertIn("remove_lineage_objects", names)
            self.assertNotIn("build_report_project", names)

    def test_protocol_mentions_update_and_stale_pxf(self):
        from report_mcp_agent.src.report import lineage_protocol

        p = lineage_protocol.protocol_dict()
        names = " ".join(s["name"] for s in p["steps"])
        blob = " ".join(s["text"] for s in p["steps"]) + " ".join(p["hard_rules"])
        self.assertIn("UPDATE", blob)
        self.assertIn("10", blob)
        self.assertIn("промежуточн", blob.lower())
        self.assertIn("recheck_sources", names)
        self.assertIn("analyze_view_like_procedure", names)
        self.assertIn("перепроверка", blob.lower())
        self.assertIn("writes_to=<то же имя view>", blob)
        self.assertNotIn("work.smd_* запрещено", blob)
        self.assertFalse(p["revision_mode"]["full_rebuild"])

    def test_schedule_dedup_and_no_target_column(self):
        from report_mcp_agent.src.report.schedule_format import format_run_order_section

        data = {
            "schedule_entries": [
                {
                    "kind": "procedure",
                    "object": "work.p_ukp",
                    "target": "work.t1",
                    "note": "",
                },
                {
                    "kind": "procedure",
                    "object": "work.p_ukp",
                    "target": "",
                    "schedule_label": "пн–пт 06:15",
                    "summary": {"typical_start_time": "06:15", "weekdays_ru_label": "пн–пт"},
                    "note": "сборка",
                },
            ],
            "lineage_steps": [],
        }
        md = format_run_order_section(data)
        self.assertEqual(md.count("`work.p_ukp`"), 1)
        self.assertIn("пн–пт 06:15", md)
        self.assertNotIn("Целевая таблица", md)
        self.assertIn("Порядок запуска", md)

    def test_diagram_wraps_names_and_prefers_typical_schedule(self):
        from report_mcp_agent.src.report import diagram_svg

        data = {
            "final_object": "s_grnplm_ld_blago_ubhq_work.qs_t_ukp_weeks_long_name",
            "lineage_steps": [{
                "procedure": "s_grnplm_ld_blago_ubhq_work.p_very_long_procedure_name_here",
                "writes_to": "s_grnplm_ld_blago_ubhq_work.qs_t_ukp_weeks_long_name",
                "reads_from": [
                    "s_grnplm_ld_blago_ubhq_in.smd_is0540_bo_je_details_h"
                ],
            }],
            "schedule_entries": [{
                "kind": "procedure",
                "object": "s_grnplm_ld_blago_ubhq_work.p_very_long_procedure_name_here",
                "last_success": "2026-10-01 06:00",
                "summary": {
                    "typical_start_time": "06:15",
                    "weekdays_ru_label": "пн–пт",
                    "schedule_label": "пн–пт 06:15",
                },
            }],
        }
        svg = diagram_svg.build_lineage_svg(data)
        self.assertIn("пн–пт 06:15", svg)
        self.assertIn("Сверху вниз", svg)
        self.assertNotIn("2026-10-01", svg)
        self.assertIn("<tspan", svg)
        self.assertIn("p_very_long", svg)
        # время в отдельной полосе — не обрезано до «пн–пт 06…»
        self.assertIn(">пн–пт 06:15</text>", svg)


if __name__ == "__main__":
    unittest.main()
