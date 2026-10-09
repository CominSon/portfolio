import sys
from pathlib import Path


def _setup_path():
    package_dir = Path(__file__).parent.absolute()
    project_root = package_dir.parent
    if not (project_root / "mail_mcp_agent").is_dir():
        cwd = Path.cwd()
        if (cwd / "mail_mcp_agent").is_dir():
            project_root = cwd
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return project_root


def main():
    project_root = _setup_path()
    from mail_mcp_agent.src.utils.logging_config import setup_logging
    from mail_mcp_agent.src.server.mcp_server import MCPServer

    setup_logging(project_root / "mail_mcp_agent")
    MCPServer().run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        raise SystemExit(1)
