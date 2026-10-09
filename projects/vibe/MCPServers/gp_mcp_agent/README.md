# Greenplum MCP — краткая инструкция

Запросы и анализ данных в Greenplum (UBHQ / WEALTHHUB).

## Первый запуск

1. **`healthcheck`** — проверка подключения к БД.
2. **`set_project_path`** — путь к открытому проекту в IDEA (для выгрузок CSV).

## Основные команды

| Задача | Что вызвать |
|--------|-------------|
| Найти таблицы | `search_tables` (до 200 результатов) |
| Колонки / DDL | `get_columns`, `get_table_ddl` |
| SELECT в чат | `run_select` (~100 строк) |
| Выгрузка в CSV | `export_query_csv` → `<проект>/export/` |
| Загрузка файла в GP | `load_file_to_table` |
| Логи процедур / PXF | `run_select` (см. DOMAIN_KNOWLEDGE в instructions MCP) |
| Расписание процедуры | `get_procedure_schedule` |

## Выгрузка CSV

CSV сохраняются в **`<проект>/export/`**, не в папку MCP Servers.
Перед выгрузкой вызовите `set_project_path`.

## Ограничения

- Чтение: SELECT, WITH, EXPLAIN.
- Запись в БД: только **`load_file_to_table`** (COPY из файла).
- Схемы: `ext`, `in`, `work`, `2prod`.

## Полный справочник

См. [MCP_TOOLS_GUIDE.md](../MCP_TOOLS_GUIDE.md) в корне `MCPServers`.
