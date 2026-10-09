from sqlalchemy import text
from connectBD_v2 import Main
from modules.criticalerror import CriticalError

class DatabaseConnection:
    def __init__(self, active_schema, logger):
        self.schema_name = active_schema
        self.logger = logger
        self.engine = None

    def return_best_engine(self):
        try:
            self.engine = Main().use_new_engine(connect_name="capgp1", schema=self.schema_name.upper())
        except Exception as e:
            self.logger.info("Проблема с подключением к БД")
            self.logger.exception(e)
            raise CriticalError from e

    def execute_in_gp_for_tables(self, query: str):
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            return conn.execute(text(query)).fetchall()

    def execute_in_gp(self, query: str):
        with self.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.execute(text(query))
 
    def get_tables(self):
        try:
            # Получаем список всех таблиц в схеме
            query = f"""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = '{self.schema_name.lower()}'
            AND table_type not ilike ('VIEW');
            """
            result = self.execute_in_gp_for_tables(query)
            tables = [row[0] for row in result]
            print(tables)
            self.logger.info(f"Получен список таблиц для схемы {self.schema_name.lower()}")
            return tables
        except Exception as e:
            self.logger.exception(f"Ошибка при получении списка таблиц из схемы {self.schema_name.lower()}: {e}")
            raise CriticalError from e
 
    def close(self):
        if self.engine:
            self.engine.dispose()
            self.logger.info(f"Соединение с схемой {self.schema_name.lower()} закрыто")
 
