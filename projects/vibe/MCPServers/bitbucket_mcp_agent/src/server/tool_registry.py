import json
import logging

from bitbucket_mcp_agent.src.tools.git_tools import (
    CheckoutBranchTool,
    CommitAndPushTool,
    GetRepoInfoTool,
    GitCommitTool,
    GitCompareRecentTool,
    GitDiffTool,
    GitFetchTool,
    GitLogTool,
    GitPullTool,
    GitPushTool,
    GitRestoreTool,
    GitStatusTool,
    HealthcheckGitTool,
    ListBranchesTool,
    PreviewFileAtCommitTool,
)
from bitbucket_mcp_agent.src.tools.mcp_sync_tools import UpdateMcpServersTool
from bitbucket_mcp_agent.src.tools.project_path_tools import (
    GetProjectPathTool,
    SetProjectPathTool,
    UseMcpCwdAsProjectTool,
)
from bitbucket_mcp_agent.src.utils.arg_coerce import normalize_tool_arguments
from bitbucket_mcp_agent.src.utils.tool_errors import build_tool_error_payload

logger = logging.getLogger("bb_mcp.tools")


class ToolRegistry(object):
    def __init__(self):
        self._tools = {
            "get_project_path": GetProjectPathTool(),
            "set_project_path": SetProjectPathTool(),
            "use_mcp_cwd_as_project": UseMcpCwdAsProjectTool(),
            "healthcheck_git": HealthcheckGitTool(),
            "get_repo_info": GetRepoInfoTool(),
            "git_status": GitStatusTool(),
            "git_diff": GitDiffTool(),
            "git_compare_recent": GitCompareRecentTool(),
            "git_log": GitLogTool(),
            "preview_file_at_commit": PreviewFileAtCommitTool(),
            "git_restore": GitRestoreTool(),
            "git_fetch": GitFetchTool(),
            "git_pull": GitPullTool(),
            "list_branches": ListBranchesTool(),
            "checkout_branch": CheckoutBranchTool(),
            "commit_and_push": CommitAndPushTool(),
            "git_commit": GitCommitTool(),
            "git_push": GitPushTool(),
            "update_mcp_servers": UpdateMcpServersTool(),
        }

    def list_schemas(self):
        return [t.schema() for t in self._tools.values()]

    def call(self, name, arguments):
        arguments = normalize_tool_arguments(arguments)
        tool = self._tools.get(name)
        if not tool:
            raise KeyError("Неизвестный tool: {0}".format(name))
        result = tool.execute(arguments)
        text = json.dumps(result, ensure_ascii=False, default=str, indent=2)
        return {"content": [{"type": "text", "text": text}]}

    def call_error(self, tool_name, message, error_type=None, hint=None, detail=None):
        payload = build_tool_error_payload(
            tool_name, message, error_type=error_type, hint=hint, detail=detail
        )
        return {
            "content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
            "isError": True,
        }
