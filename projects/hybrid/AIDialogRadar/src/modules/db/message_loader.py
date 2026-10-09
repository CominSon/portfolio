from datetime import datetime, timedelta
from src.modules.db.postgres_manager import PostgresManager


class MessageLoader:
    def __init__(self, logger):
        self.logger = logger
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)

    def load_recent_messages(self):
        """Выгружаем полученные из чата сообщения"""
        try:
            query = """
                SELECT chat_id, date, text
                FROM messages
                ORDER BY date
            """
            return self.postgres_manager.execute_sql_query(query, fetchall=True)
        except Exception as e:
            self.logger.error(f"Ошибка извлечения эталонных данных: {e}")
            return []


