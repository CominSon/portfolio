# report-project-mcp v3.2

Канон: **`get_report_context` → `lineage_protocol`**.

## Структура папок
```
УКП Недельный/          ← название отчёта (можно кириллица)
  ukp_weeks/            ← object_slug (из final_table / object_folder) = project_root
    docs/
    sql/ddl/objects/sources/
    sql/ddl/objects/intermediate/
    sql/ddl/objects/final/
    sql/ddl/functions/
    sql/dml/
    python/             ← sync_all_ddl.py, create_structure_md.py
    agent_registry/
```

## Протокол
1. `get_link_object` → сырой список; разбор функции/view  
2. View = шаг как процедура; helper → `related_transforms`  
3. Рекурсия; `inventory.sources` ≠ промежуточные  
4. `in.smd_*` ≈ PXF; `work.smd_*` = промежуточная  
5. Перепроверка sources  

## Артефакты
- SVG сверху вниз; день+время полностью  
- TECHNICAL §5 — одна таблица по порядку запуска  
- DDL: `refresh_project_ddl` (sources/intermediate/final)  
