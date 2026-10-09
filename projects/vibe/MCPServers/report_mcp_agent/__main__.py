"""Точка входа: python -m report_mcp_agent"""

import sys
from pathlib import Path


def _setup_path():
    package_dir = Path(__file__).parent
    try:
        package_dir = package_dir.resolve()
    except OSError:
        package_dir = package_dir.absolute()

    project_root = package_dir.parent
    if not (project_root / "report_mcp_agent").is_dir():
        cwd = Path.cwd()
        if (cwd / "report_mcp_agent").is_dir():
            project_root = cwd

    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return project_root


def main():
    project_root = _setup_path()
    from report_mcp_agent.src.utils.logging_config import setup_logging
    from report_mcp_agent.src.server.mcp_server import MCPServer

    setup_logging(project_root / "report_mcp_agent")
    MCPServer().run()


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
