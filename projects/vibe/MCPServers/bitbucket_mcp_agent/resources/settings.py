"""Конфигурация MCP Bitbucket / Git."""

import os

BITBUCKET_HOST = "df-bitbucket.ca.sbrf.ru"
WEALTHHUB_PROJECT = "WEALTHHUB"
WEALTHHUB_URL_FRAGMENTS = (
    "/projects/{0}/".format(WEALTHHUB_PROJECT),
    "/scm/wealthhub/",
    "/scm/{0}/".format(WEALTHHUB_PROJECT.lower()),
)

# Репозиторий dashboards: push в master запрещён
DASHBOARDS_REPO_SLUG = "dashboards"
PROTECTED_BRANCHES = ("master", "main")

NOTERBALL_XLSX = os.environ.get(
    "BB_NOTERBALL_XLSX",
    r"Z:\Exchange\Maksim\Python Scripts\Рабочие области\working\kkts\pen_is.xlsx",
)
NOTERBALL_SHEET = "Лист1"

# Сохранённый корень git-проекта (при нескольких репозиториях в IDEA)
PROFILE_SUBDIR = "bb_mcp_config"
PROFILE_FILENAME = "project.json"

# Токены подтверждения (в памяти процесса, TTL секунд)
CONFIRM_TOKEN_TTL_SEC = 600

# Каталог локальных MCP-серверов (cwd GigaIDE)
MCP_SERVERS_LOCAL_ROOT = os.environ.get("MCP_SERVERS_ROOT", r"U:\MCP Servers")

# Источник актуальных скриптов: wealthhub/python, ветка master, папка «MCP Servers»
MCP_SOURCE_REPO_URL = os.environ.get(
    "MCP_SOURCE_REPO_URL",
    "https://df-bitbucket.ca.sbrf.ru/scm/wealthhub/python.git",
)
MCP_SOURCE_BRANCH = os.environ.get("MCP_SOURCE_BRANCH", "master")
MCP_SOURCE_SUBDIR = os.environ.get("MCP_SOURCE_SUBDIR", "MCP Servers")

# Кэш shallow-клона python.git (не путать с project_path пользователя)
MCP_SYNC_CACHE_DIRNAME = "mcp_sync_cache"

# Правила GigaCode в профиле пользователя
GIGACODE_RULES_REL = os.path.join(".gigacode", "rules", "mcp.md")
GIGACODE_RULES_SOURCE_NAME = "GIGACODE_MCP_RULES.txt"

# Известные MCP-пакеты → имя в GigaIDE + краткое описание для чата
KNOWN_MCP_PACKAGES = {
    "gp_mcp_agent": {
        "ide_name": "greenplum",
        "module": "gp_mcp_agent",
        "description": (
            "Greenplum: SQL, DDL, поиск таблиц/функций, логи, "
            "get_link_object / get_function / lineage-помощники."
        ),
    },
    "bitbucket_mcp_agent": {
        "ide_name": "bitbucket",
        "module": "bitbucket_mcp_agent",
        "description": (
            "Git WEALTHHUB: status/diff/commit/push, откат файлов, "
            "обновление локальных MCP Servers из python.git."
        ),
    },
    "mail_mcp_agent": {
        "ide_name": "mail",
        "module": "mail_mcp_agent",
        "description": "Корпоративная почта omega: поиск писем, вложения, отправка.",
    },
    "report_mcp_agent": {
        "ide_name": "report-project",
        "module": "report_mcp_agent",
        "description": (
            "Проекты отчётности: lineage, BUSINESS/TECHNICAL, SVG-схема, "
            "ревизии по диалогу с агентом."
        ),
    },
}

# Не трогать при синхронизации (локальное состояние / мусор)
MCP_SYNC_SKIP_DIR_NAMES = frozenset({
    "__pycache__",
    ".git",
    ".cache",
    "mcp_sync_cache",
    "bb_mcp_config",
    "gp_mcp_config",
    "mail_mcp_config",
    "report_mcp_config",
})
MCP_SYNC_SKIP_FILE_SUFFIXES = (".pyc", ".pyo", ".pyd")

SERVER_NAME = "bitbucket-git-mcp"
SERVER_VERSION = "1.1.0"

SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]
DEFAULT_PROTOCOL_VERSION = "2024-11-05"

DOMAIN_KNOWLEDGE = """
Git: get_project_path → set_project_path при смене репозитория в IDEA.
Коммит и push одним вызовом: commit_and_push (без dot-файлов/папок).
Чтение (git_status, git_diff, git_compare_recent) — без подтверждений.
git push --force запрещён. Push в master/main dashboards запрещён.
«Обнови мои MCP Серверы» → update_mcp_servers (python.git master → U:\\MCP Servers).
""".format(host=BITBUCKET_HOST, project=WEALTHHUB_PROJECT)
