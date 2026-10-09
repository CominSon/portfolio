from mcp_workspace_config.arg_aliases import normalize_report_arguments


def coerce_project_args(arguments):
    return normalize_report_arguments(arguments or {})
