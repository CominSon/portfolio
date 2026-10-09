"""Безопасные пути на сетевых дисках (U:\\) — без resolve(), WinError 5."""

from pathlib import Path


def safe_absolute(path):
    p = Path(path)
    try:
        return p.resolve()
    except (OSError, PermissionError):
        return p.absolute()


def package_root(from_file):
    """
    Корень пакета mail_mcp_agent / bitbucket_mcp_agent.
    Не использует resolve() — совместимо с U:\\MCP Servers.
    """
    p = Path(from_file).absolute()
    if p.name == "__main__.py":
        return p.parent
    # .../agent/src/.../module.py → parents[1] == agent
    return p.parents[1]
