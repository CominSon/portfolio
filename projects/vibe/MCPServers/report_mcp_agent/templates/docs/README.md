# {{REPORT_TITLE}}

Проект отчёта Greenplum.

| | |
|--|--|
| Финальная витрина | `{{FINAL_OBJECT}}` |
| Техническое описание | [TECHNICAL.md](TECHNICAL.md) |
| Бизнес-описание | [BUSINESS.md](BUSINESS.md) |
| Run order | [../sql/dml/00_run_order.sql](../sql/dml/00_run_order.sql) |

## Как дорабатывать

Агент использует GP MCP для lineage/DDL/семплов и report MCP для файлов/manifest.
Замечания пользователя → `add_report_revision` (не пересоздавать проект).
