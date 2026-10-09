"""Безопасные пути на сетевых дисках (U:\\) — делегирование в mcp_workspace_config."""

from pathlib import Path

from mcp_workspace_config.safe_path import probe_write_access, safe_absolute


def package_root(from_file):
    p = Path(from_file).absolute()
    if p.name == "__main__.py":
        return p.parent
    return p.parents[1]
