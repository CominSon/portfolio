from __future__ import annotations
from typing import Any, Dict
import os

class Diagnostics:
    def __init__(self, pg_manager, llm_manager, logger):
        self.pg = pg_manager
        self.llm = llm_manager
        self.logger = logger

    def check_db(self) -> Dict[str, Any]:
        self.logger.info("Проверка БД: SELECT 1")
        row = self.pg.execute_sql_query("SELECT 1 AS ok", fetchall=False)
        return {"ok": (row or {}).get("ok") == 1}

    def check_os_ub_nav_access(self) -> Dict[str, Any]:
        table = os.getenv("OS_UB_NAV_TABLE")
        self.logger.info(f"Проверка доступа к основной таблице: {table}")
        row = self.pg.execute_sql_query(f"SELECT COUNT(*) AS cnt FROM {table} LIMIT 1", fetchall=False)
        return {"table": table, "count": int(row["cnt"]) if row and "cnt" in row else None}

    def check_llm(self) -> Dict[str, Any]:
        self.logger.info("Проверка LLM: тестовый JSON")
        system = 'Верни строго JSON: {"ping": "pong"}'
        payload = {"test": True}
        res = self.llm.generate_json(system_prompt=system, user_payload=payload)
        return {"response": res}
