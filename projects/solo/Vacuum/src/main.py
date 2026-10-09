import sys 
import os

current_dir = os.path.dirname(os.path.abspath(__file__)) 
sys.path.append(current_dir)

import logging
from settings import Settings, Logging
from modules.database import DatabaseConnection
from modules.vacuum import VacuumManager
from modules.criticalerror import CriticalError

class Main:
    def __init__(self):
        self.logger_setting: Logging = Logging()
        self.settings: Settings = Settings()
        

    def start(self):
        logger = self.logger_setting.basic_configuration(table_name="vacuum_logs")
        for schema in self.settings.SCHEMAS:
            try:
                # Подключаемся к БД
                db_conn = DatabaseConnection(schema, logger)
                db_conn.return_best_engine()
    
                # Инициализируем менеджер вакуума
                vacuum_manager = VacuumManager(db_conn, logger)
                vacuum_manager.vacuum_all_tables()
    
                # Закрываем соединение
                db_conn.close()
            except Exception as e:
                logger.exception(f"Общая ошибка при обработке схемы {schema}: {e}")
                raise CriticalError from e
 
if __name__ == '__main__':
    main: Main = Main()
    main.start()
