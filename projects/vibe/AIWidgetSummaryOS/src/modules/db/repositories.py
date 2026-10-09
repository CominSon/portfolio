from __future__ import annotations
from typing import Any, Dict, List
import os
import json
from modules.common.sql_utils import safe_col

class MetadataRepository:
    """Чтение метаданных виджетов/полей из БД."""

    def __init__(self, pg_manager, logger):
        self.pg = pg_manager
        self.logger = logger
        self.schema = os.getenv("AI_META_SCHEMA")

    def get_widgets_by_group(self, group_widget: str) -> List[Dict[str, Any]]:
        q = f"""
            SELECT
                id_widget,
                group_widget,
                widget_title,
                widget_description_short,
                axis_json,
                dependencies_json,
                policy_json,
                prompt_template_id
            FROM {self.schema}.ai_os_ub_widget_meta
            WHERE group_widget = %s
            ORDER BY id_widget
        """
        self.logger.info(f"Загружаю список виджетов по группе: {group_widget}")
        rows = self.pg.execute_sql_query(q, group_widget, fetchall=True) or []
        for r in rows:
            r["axis"] = json.loads(r["axis_json"]) if r.get("axis_json") else {}
            r["dependencies"] = json.loads(r["dependencies_json"]) if r.get("dependencies_json") else []
            r["policy"] = json.loads(r["policy_json"]) if r.get("policy_json") else {}
        return rows
    
    def get_all_groups(self) -> List[str]:
        q = f"""
            SELECT DISTINCT group_widget
            FROM {self.schema}.ai_os_ub_widget_meta
            WHERE NULLIF(TRIM(COALESCE(group_widget, '')), '') IS NOT NULL
            ORDER BY group_widget
        """
        rows = self.pg.execute_sql_query(q, fetchall=True) or []
        return [str(r["group_widget"]).strip() for r in rows if r.get("group_widget") is not None]


    def get_widget_fields(self, widget_id: int) -> List[Dict[str, Any]]:
        
        q = f"""
            SELECT id_widget, field_name, role, field_description_short, rules_json, priority
            FROM {self.schema}.ai_os_ub_widget_field_meta
            WHERE id_widget = %s
            ORDER BY field_name
        """
        self.logger.info(f"Загружаю метаданные полей для виджета: {widget_id}")
        rows = self.pg.execute_sql_query(q, widget_id, fetchall=True) or []
        for r in rows:
            r["rules"] = json.loads(r["rules_json"]) if r.get("rules_json") else {}
        return rows

    def get_widget_dependencies(self, widget_id: int) -> List[Dict[str, Any]]:
        
        q = f"""
            SELECT dependencies_json
            FROM {self.schema}.ai_os_ub_widget_meta
            WHERE id_widget = %s
        """
        row = self.pg.execute_sql_query(q, widget_id, fetchall=False) or {}
        deps_json = row.get("dependencies_json")
        return json.loads(deps_json) if deps_json else []
    
    def get_prompt_template(self, template_id: int) -> Dict[str, Any]: 
        q = f"""
            SELECT prompt_json
            FROM {self.schema}.ai_os_ub_prompt_templates
            WHERE template_id = %s AND is_active = true
            ORDER BY updated_at DESC
            LIMIT 1
        """
        self.logger.info(f"Загружаю шаблон промптов из БД: template_id={template_id}")
        row = self.pg.execute_sql_query(q, template_id, fetchall=False) or {}
        raw = row.get("prompt_json")
        if not raw:
            raise RuntimeError(f"Не найден шаблон промптов в БД: template_id={template_id}")

        # В БД это может быть TEXT (строка JSON) — приводим к dict
        return json.loads(raw) if isinstance(raw, str) else raw



class NavDataRepository:
    """Чтение данных из основной таблицы os_ub_nav."""

    def __init__(self, pg_manager, logger):
        self.pg = pg_manager
        self.logger = logger
        self.table = os.getenv("OS_UB_NAV_TABLE")

    def get_last_versions(self, widget_id: int, limit: int = 2) -> List[str]:
        q = f"""
            SELECT DISTINCT date_update
            FROM {self.table}
            WHERE id_widget = %s AND date_update IS NOT NULL
            ORDER BY date_update DESC
            LIMIT {limit}
        """
        rows = self.pg.execute_sql_query(q, widget_id, fetchall=True) or []
        self.logger.info(f"[SQL] get_last_versions: {q.strip()} | params={widget_id, limit}")
        return [str(r["date_update"]) for r in rows]

    def fetch_widget_rows_for_versions(self, widget_id: int, versions: List[str]) -> List[Dict[str, Any]]:
        if not versions:
            return []
        placeholders = ",".join(["%s"] * len(versions))
        q = f"""
            SELECT *
            FROM {self.table}
            WHERE id_widget = %s
              AND date_update IN ({placeholders})
        """
        args = [widget_id] + versions
        self.logger.info(f"Загружаю строки виджета {widget_id} для версий date_update={versions}")
        return self.pg.execute_sql_query(q, *args, fetchall=True) or []
    
    def get_latest_period_value1(self, widget_id: int, last_date_update: str, period_field: str, flag_field: str) -> str:
        """
        Возвращает актуальный период (max(period_field)) для последней date_update,
        с исключением строк flag_field ='План'.
        """
        period_field = safe_col(period_field)
        flag_field = safe_col(flag_field)
        q = f"""
            SELECT MAX({period_field}) AS max_value
            FROM {self.table}
            WHERE id_widget = %s
            AND date_update = %s
            AND POSITION('план' IN LOWER(COALESCE({flag_field}::text, ''))) = 0
        """
        row = self.pg.execute_sql_query(q, widget_id, last_date_update, fetchall=False) or {}
        self.logger.info(f"[SQL] get_latest_period_value1: {q.strip()} | params={widget_id, last_date_update}")
        return row.get("max_value")


    def fetch_rows_for_period_and_versions(
        self,
        widget_id: int,
        period_value: str,
        versions: list[str],
        period_field: str,
        flag_field: str,
        fact_field: str | None = None,
        last_date_update: str | None = None,
    ) -> list[dict]:
        """
        Загружает строки виджета для конкретного периода по списку date_update.
        Фильтры:
        - исключаем сценарии с пометкой "План";
        - для исторических версий (не последней) можно исключить строки с пустым фактом.
        """
        if not versions:
            return []
        placeholders = ",".join(["%s"] * len(versions))
        period_field = safe_col(period_field)
        flag_field = safe_col(flag_field)
        fact_condition = ""
        if fact_field and last_date_update:
            fact_field = safe_col(fact_field)
            fact_condition = (
                f" AND (date_update = %s "
                f"OR NULLIF(TRIM(COALESCE({fact_field}::text, '')), '') IS NOT NULL)"
            )
        q = f"""
            SELECT *
            FROM {self.table}
            WHERE id_widget = %s
            AND {period_field} = %s
            AND date_update IN ({placeholders})
            AND POSITION('план' IN LOWER(COALESCE({flag_field}::text, ''))) = 0
            {fact_condition}
            order by date_update desc

        """
        args = [widget_id, period_value] + versions
        if fact_field and last_date_update:
            args.append(last_date_update)
        self.logger.info(f"[SQL] fetch_rows_for_period_and_versions: {q.strip()} | params={args}")
        return self.pg.execute_sql_query(q, *args, fetchall=True) or []

