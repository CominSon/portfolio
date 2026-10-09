"""Конфигурация MCP-сервера Greenplum."""

GP_CONNECTION_NAME = "capgp1_in"

GP_ALLOWED_SCHEMAS = [
    "s_grnplm_ld_blago_ubhq_ext",
    "s_grnplm_ld_blago_ubhq_in",
    "s_grnplm_ld_blago_ubhq_work",
    "s_grnplm_ld_blago_ubhq_2prod",
]

# external → ext, materialized → in
GP_EXTERNAL_SCHEMA = GP_ALLOWED_SCHEMAS[0]
GP_MATERIALIZED_SCHEMA = GP_ALLOWED_SCHEMAS[1]
GP_MATERIALIZED_PREFIX = "smd_"

GP_STATEMENT_TIMEOUT_MS = 120_000
GP_SELECT_ROW_LIMIT = 100
GP_SEARCH_TABLES_LIMIT = 50

# Учётная запись планировщиков / manage_backend (НЕ путать с УЗ того, кто подключён к MCP)
GP_BACKEND_USER = "18764734"
GP_SCHEDULER_DISPLAY_NAME = "Павленко Максим Юрьевич"
GP_MANAGE_BACKEND_SCHEMA = "s_grnplm_ld_blago_ubhq_in"
GP_MANAGE_BACKEND_FUNCTION = "manage_backend_18764734"

GP_FIELD_COMPARE_ROW_LIMIT = 100
GP_FIELD_COMPARE_PREVIEW_LIMIT = 10
GP_LINEAGE_FUNCTION_SEARCH_LIMIT = 30

# Выгрузка CSV: <проект>/export или GP_MCP_EXPORT_DIR
GP_EXPORT_SUBDIR = "export"
GP_EXPORT_BATCH_SIZE = 5000
# 0 = без лимита строк (ограничение только statement_timeout БД)
GP_EXPORT_MAX_ROWS = 0

PROFILE_SUBDIR = "gp_mcp_config"
PROFILE_FILENAME = "project_profile.json"
GP_SEARCH_TABLES_MAX_LIMIT = 200

# Логи планировщика процедур и PXF (схема in)
GP_LOGS_SCHEMA = GP_MATERIALIZED_SCHEMA
GP_LOGS_PROCEDURE_TABLE = "logs_procedure"
GP_LOGS_PXF_TABLE = "logs_pxf_table"
# procedure_name без схемы в logs_procedure относится к work
GP_DEFAULT_PROCEDURE_SCHEMA = "s_grnplm_ld_blago_ubhq_work"
GP_LINK_OBJECT_FUNCTION = "f_get_link_object"
GP_LINK_OBJECT_SCHEMAS = [
    GP_MATERIALIZED_SCHEMA,
    GP_DEFAULT_PROCEDURE_SCHEMA,
]
GP_LOGS_DEFAULT_LIMIT = 50
GP_LOGS_MAX_LIMIT = 200

# status в logs_procedure и logs_pxf_table — только два значения (текст)
GP_LOG_STATUS_DONE = "DONE"
GP_LOG_STATUS_FAILED = "FAILED"

# PXF: ext.<table> -> in.smd_<table>; полная переливка — pxf_truncate_and_insert
GP_PXF_TRUNCATE_FUNCTION = "pxf_truncate_and_insert"
GP_PXF_FILTERED_FUNCTION = "pxf_delete_and_insert_filtered"

SERVER_NAME = "gp-greenplum-mcp"
SERVER_VERSION = "1.3.1"

DOMAIN_KNOWLEDGE = """
=== Универсальный доступ к данным ===
Любые вопросы по логам, датам, спискам таблиц, агрегатам — **run_select** или **export_query_csv**.
Пользователь формулирует задачу обычным языком; агент пишет SQL по схеме и колонкам ниже.

=== Общее для логов планировщика (текстовые поля + даты) ===
Колонки status, logs_text и имя объекта — **text**. date_start, date_end — даты/время.
Поле **status** — **только** '{done}' или '{failed}' (регистр как в БД, обычно верхний).
Успех: status = '{done}'. Ошибка: status = '{failed}'.
Не используй SUCCESS/success/ok, LIKE '%fail%' и прочие догадки — только DONE/FAILED.

=== Логи процедур: {logs_schema}.{logs_proc} ===
Колонки: procedure_name, status, date_start, date_end, logs_text.
procedure_name без схемы — процедуры {proc_default}; с префиксом in — in.
Типичное время запуска: get_procedure_schedule (агрегат по логам).

=== Логи PXF (переливка ext → in.smd_*): {logs_schema}.{logs_pxf} ===
Колонки: table_name, status, date_start, date_end, logs_text (та же схема, что logs_procedure,
но вместо procedure_name — table_name: имя таблицы на **ext**, без smd_).
Полная переливка: {logs_schema}.{pxf_full}(table_name); срез: {logs_schema}.{pxf_filt}.
ext-таблицы: {ext_schema}, целевые smd_*: {in_schema}.

Пример — последний успех (DONE) по списку витрин:
  WITH wanted(name) AS (VALUES ('PDS_NAVIGATOR'), ('TABLE2'))
  SELECT w.name,
         MAX(l.date_start) FILTER (WHERE l.status = '{done}') AS last_successful_load,
         MAX(l.date_start) FILTER (WHERE l.status = '{failed}') AS last_failed_load,
         MAX(l.date_start) AS last_run_any_status
  FROM wanted w
  LEFT JOIN {logs_schema}.{logs_pxf} l
    ON l.table_name ILIKE '%' || w.name || '%'
   AND l.date_start >= TIMESTAMP '2026-01-01'
  GROUP BY w.name;

Отвечай по last_successful_load (DONE), не путай с last_run_any_status.

=== Выгрузки ===
export_query_csv / export_csv=true в run_select → <проект>/export/ (set_project_path).
""".format(
    done=GP_LOG_STATUS_DONE,
    failed=GP_LOG_STATUS_FAILED,
    logs_schema=GP_LOGS_SCHEMA,
    logs_proc=GP_LOGS_PROCEDURE_TABLE,
    proc_default=GP_DEFAULT_PROCEDURE_SCHEMA,
    logs_pxf=GP_LOGS_PXF_TABLE,
    pxf_full=GP_PXF_TRUNCATE_FUNCTION,
    pxf_filt=GP_PXF_FILTERED_FUNCTION,
    ext_schema=GP_EXTERNAL_SCHEMA,
    in_schema=GP_MATERIALIZED_SCHEMA,
)

# Поддерживаемые версии протокола MCP (от новой к старой)
SUPPORTED_PROTOCOL_VERSIONS = [
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
]
DEFAULT_PROTOCOL_VERSION = "2024-11-05"
