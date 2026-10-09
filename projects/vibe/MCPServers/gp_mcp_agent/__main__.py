"""Точка входа: python -m gp_mcp_agent"""

import sys
from pathlib import Path


def _setup_path():
    # type: () -> Path
    """Добавляет корень проекта (родитель gp_mcp_agent) в PYTHONPATH."""
    package_dir = Path(__file__).parent
    # resolve() на сетевых дисках (U:\) часто даёт WinError 5 — Access denied
    try:
        package_dir = package_dir.resolve()
    except OSError:
        package_dir = package_dir.absolute()

    project_root = package_dir.parent

    # cwd в GigaCode = корень MCPServers; запасной вариант, если __file__ относительный
    if not (project_root / "gp_mcp_agent").is_dir():
        cwd = Path.cwd()
        if (cwd / "gp_mcp_agent").is_dir():
            project_root = cwd

    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return project_root


def main():
    project_root = _setup_path()

    from gp_mcp_agent.src.utils.logging_config import setup_logging
    from gp_mcp_agent.src.server.mcp_server import MCPServer

    setup_logging(project_root / "gp_mcp_agent")
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        try:
            sys.stderr.flush()
        except OSError:
            pass
        raise SystemExit(1)
