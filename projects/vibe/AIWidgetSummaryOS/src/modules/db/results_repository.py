from datetime import datetime
from typing import Optional


class ResultsRepository:
    def __init__(self, pg_manager, logger, schema: str = "s_grnplm_ld_blago_ubhq_work"):
        self.pg = pg_manager
        self.logger = logger
        self.schema = schema

    def insert_result(self, group_name: str, report_path: str) -> None:
        if not report_path:
            raise ValueError("report_path пустой: отчёт не был сохранён на диск.")
        dt = datetime.now()
        with open(report_path, "r", encoding="utf-8") as f:
            text = f.read()
        sql = f"""
        INSERT INTO {self.schema}.ai_os_ub_results (date_update, group_name, text)
        VALUES (%s, %s, %s)
        """
        self.pg.execute_sql_query(sql, dt, group_name, text)

        self.logger.info(f"[DB] ai_os_ub_results загружено: group_name={group_name}, date_update={dt.isoformat(timespec='seconds')}")
