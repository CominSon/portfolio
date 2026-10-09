class VacuumManager:
    def __init__(self, db_connection, logger):
        self.db = db_connection
        self.logger = logger
        
 
    def vacuum_table(self, table_name):
        try:
            # Выполняем VACUUM FULL и ANALYZE для таблицы
            query = f"VACUUM FULL ANALYZE {self.db.schema_name}.{table_name};"
            self.db.execute_in_gp(query=query)
            #self.db.engine.execute(query)
            self.logger.info(f"[{self.db.schema_name}::{table_name}][Выполнен VACUUM FULL ANALYZE]")
        except Exception as e:
            self.logger.exception(f"Ошибка при выполнении VACUUM для таблицы {table_name} в схеме {self.db.schema_name}: {e}")
            pass
 
    def vacuum_all_tables(self):
        tables = self.db.get_tables()
        for table in tables:
            self.vacuum_table(table)
        self.logger.info(f"[Выполнен VACUUM FULL ANALYZE выполнен на всех объектах]")
        self.logger.info(f"---------------------------------------------------------------------------")
