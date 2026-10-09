"""Конфигурация MCP-сервера проектов отчётов (agent-driven, v3.2)."""

import os

SERVER_NAME = "report-project-mcp"
SERVER_VERSION = "3.2.0"

SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

DEFAULT_FINAL_SCHEMA = os.environ.get(
    "REPORT_DEFAULT_SCHEMA",
    "s_grnplm_ld_blago_ubhq_in",
)

REPORTS_SUBDIR = os.environ.get("REPORT_PROJECTS_SUBDIR", "reports")

AGENT_REGISTRY_DIR = "agent_registry"
MANIFEST_FILENAME = "REPORT_MANIFEST.json"
STRUCTURE_SUMMARY_FILENAME = "structure_summary.json"
MANIFEST_VERSION = 3

GP_IN_SCHEMA = "s_grnplm_ld_blago_ubhq_in"
GP_EXT_SCHEMA = "s_grnplm_ld_blago_ubhq_ext"
GP_WORK_SCHEMA = "s_grnplm_ld_blago_ubhq_work"
GP_LOGS_PXF = "{0}.logs_pxf_table".format(GP_IN_SCHEMA)
GP_LOGS_PROC = "{0}.logs_procedure".format(GP_IN_SCHEMA)

AI_GLOSSARY_TABLE = os.environ.get(
    "REPORT_AI_GLOSSARY_TABLE",
    "{0}.ai_ubhq_term_glossary".format(GP_WORK_SCHEMA),
)
AI_GLOSSARY_COLUMNS = ("term", "definition")

SAMPLE_ROW_LIMIT = 5
ALLOWED_SAMPLE_SCHEMA_SUFFIX = "_in"
SAMPLE_TABLE_PREFIX = "smd_"

ALLOWED_DOC_FILES = ("TECHNICAL.md", "BUSINESS.md")
FORBIDDEN_DOC_NAMES = ("PERFORMANCE.md", "RUNBOOK.md", "LOGIC.md", "DML.md")


def _build_domain_knowledge():
    from report_mcp_agent.src.report.lineage_protocol import protocol_instructions_block

    return """
report-project-mcp v3.2 — workspace. GP MCP = данные; report = файлы/manifest.

Цикл: start/resume → get_report_context (ОБЯЗАТЕЛЬНО) → идти по lineage_protocol →
upsert_lineage_step / upsert_schedule_entry / write_report_file → render_report_docs →
детальный BUSINESS → validate.

{protocol}

Manifest: agent_registry/REPORT_MANIFEST.json. README в корне.
Glossary: {glossary} (чтение; запись только с согласия).
DDL: refresh_project_ddl / sync_all_ddl.py — не выдумывать.
""".format(
        protocol=protocol_instructions_block(GP_IN_SCHEMA),
        glossary=AI_GLOSSARY_TABLE,
    )


DOMAIN_KNOWLEDGE = _build_domain_knowledge()
