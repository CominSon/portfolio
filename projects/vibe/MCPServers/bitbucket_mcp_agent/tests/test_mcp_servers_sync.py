"""Юнит-тесты сравнения деревьев MCP sync (без Bitbucket)."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from bitbucket_mcp_agent.src.git import mcp_servers_sync as sync


class CompareTreesTests(unittest.TestCase):
    def test_identical(self):
        with tempfile.TemporaryDirectory() as td:
            a = Path(td) / "a"
            b = Path(td) / "b"
            a.mkdir()
            b.mkdir()
            (a / "f.py").write_text("x", encoding="utf-8")
            (b / "f.py").write_text("x", encoding="utf-8")
            diff = sync.compare_trees(a, b)
            self.assertFalse(diff["has_diff"])

    def test_changed_and_copy(self):
        with tempfile.TemporaryDirectory() as td:
            local = Path(td) / "local"
            remote = Path(td) / "remote"
            local.mkdir()
            remote.mkdir()
            (local / "f.py").write_text("old", encoding="utf-8")
            (remote / "f.py").write_text("new", encoding="utf-8")
            (remote / "g.py").write_text("added", encoding="utf-8")
            result = sync.sync_directory(local, remote, dry_run=False)
            self.assertTrue(result["has_diff"])
            self.assertEqual((local / "f.py").read_text(encoding="utf-8"), "new")
            self.assertEqual((local / "g.py").read_text(encoding="utf-8"), "added")

    def test_gigaide_json_uses_u_drive(self):
        frag = sync.build_gigaide_server_json("bitbucket_mcp_agent")
        self.assertIn("bitbucket", frag)
        self.assertEqual(frag["bitbucket"]["cwd"], r"U:\MCP Servers")
        self.assertIn(r"U:\MCP Servers", frag["bitbucket"]["env"]["PYTHONPATH"])


if __name__ == "__main__":
    unittest.main()
