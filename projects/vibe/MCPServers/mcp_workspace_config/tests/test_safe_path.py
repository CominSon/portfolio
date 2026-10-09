"""Тесты safe_path на сетевых путях."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp_workspace_config.safe_path import probe_write_access, safe_absolute


class SafePathTest(unittest.TestCase):
    def test_probe_write_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = probe_write_access(tmp)
            self.assertTrue(r["writable"])

    def test_windows_drive_skips_resolve(self):
        with mock.patch("os.name", "nt"):
            p = safe_absolute(r"U:\BDProjects\foo")
            self.assertEqual(p, Path(r"U:\BDProjects\foo").absolute())


if __name__ == "__main__":
    unittest.main()
