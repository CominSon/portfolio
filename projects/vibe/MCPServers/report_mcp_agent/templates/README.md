# {{REPORT_TITLE}}

Проект отчёта Greenplum (UBHQ).

| | |
|--|--|
| Финальная витрина | `{{FINAL_OBJECT}}` |
| Object-папка | `{{OBJECT_FOLDER}}` |
| Техническое описание | [docs/TECHNICAL.md](docs/TECHNICAL.md) |
| Бизнес-описание | [docs/BUSINESS.md](docs/BUSINESS.md) |
| Схема lineage | [docs/lineage.svg](docs/lineage.svg) |
| Run order | [sql/dml/00_run_order.sql](sql/dml/00_run_order.sql) |
| Manifest | [agent_registry/REPORT_MANIFEST.json](agent_registry/REPORT_MANIFEST.json) |
| Справочник терминов AI | `{{GLOSSARY_TABLE}}` |

## Как работать

1. Агент собирает lineage через **GP MCP** (в т.ч. свои SQL к logs_pxf / logs_procedure).
2. Для `in.smd_*`: в PXF-логах искать **точное** имя без `smd_`; если нет / DONE старше 10д — `p_copy*` на схеме in. `work.smd_*` — промежуточная таблица, не PXF.
3. Замечания пользователя → доработка **этого** проекта (revision), с каскадным обновлением docs/DDL/SVG.
4. Обновить DDL из БД: `python python/sync_all_ddl.py` → `objects/sources|intermediate|final/` + `functions/`.
5. Обновить карту файлов: `python python/create_structure_md.py`.
