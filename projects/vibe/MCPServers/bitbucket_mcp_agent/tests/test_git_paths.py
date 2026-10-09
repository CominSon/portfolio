"""Тест: unwrap GigaCode {content: ...} и to_repo_relative_path."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bitbucket_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments


class ArgCoerceTest(unittest.TestCase):
    def test_unwrap_content(self):
        args = normalize_tool_arguments({
            "path": {"content": "U:/BDProjects/dashboards/a.sql"},
            "commits_back": {"content": "1"},
        })
        self.assertEqual(args["path"], "U:/BDProjects/dashboards/a.sql")
        self.assertEqual(args["commits_back"], "1")


class RepoRelativePathTest(unittest.TestCase):
    def test_absolute_to_relative(self):
        from bitbucket_mcp_agent.src.git import git_runner

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sql").mkdir()
            f = root / "sql" / "a.sql"
            f.write_text("x", encoding="utf-8")
            with patch.object(git_runner, "require_git_repo", return_value=str(root)):
                rel = git_runner.to_repo_relative_path(str(f))
            self.assertEqual(rel.replace("\\", "/"), "sql/a.sql")


if __name__ == "__main__":
    unittest.main()
