import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gp_mcp_agent.src.utils import csv_export


class TestCsvExport(unittest.TestCase):
    def test_write_sql_to_csv(self):
        rows = [
            {"missing_value": 1, "extra": "x"},
            {"missing_value": 2, "extra": "y"},
        ]

        def fake_iter(sql, params=None):
            for r in rows:
                yield r

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "gp_mcp_agent.src.utils.csv_export.project_exports_dir"
            ) as mdir:
                mdir.return_value = Path(tmp)
                with mock.patch(
                    "gp_mcp_agent.src.utils.csv_export.db_manager.fetch_iter",
                    side_effect=fake_iter,
                ):
                    result = csv_export.write_sql_to_csv(
                        "SELECT 1",
                        "test_export",
                        column_order=["missing_value"],
                    )

            self.assertTrue(result["ok"])
            self.assertEqual(result["exported_rows"], 2)
            path = result["export_path"]
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith(".csv"))

            with open(path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                data = list(reader)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[0]["missing_value"], "1")


if __name__ == "__main__":
    unittest.main()
