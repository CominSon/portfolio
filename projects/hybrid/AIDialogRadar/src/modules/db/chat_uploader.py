from src.modules.db.postgres_manager import PostgresManager


class ChatUploader:
    def __init__(self, logger):
        self.logger = logger
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)

    def upload_chat(self, chat_id: int):
        """Добавляет ID чата в таблицу chats, если он еще не добавлен."""
        try:
            query = """INSERT INTO chats (id) VALUES (%s) ON CONFLICT (id) DO NOTHING"""
            self.postgres_manager.execute_sql_query(query, [chat_id])
            self.logger.info(f"{chat_id}: Чат добавлен в таблицу chats")
        except Exception as e:
            self.logger.error(f"{chat_id}: Ошибка добавления чата: {e}")
            raise

    def truncate_messages(self):
        """Полная очистка таблицы с сообщениями"""
        try:

            query = """TRUNCATE TABLE messages"""
            self.postgres_manager.execute_sql_query(query)
            self.logger.info(f"Таблица messages очищена")
        except Exception as e:
            self.logger.error(f"Ошибка очистки таблицы messages: {e}")
            raise

    def upload_messages(self, chat_id: int, messages: list):
        """Загружает список сообщений в таблицу messages."""
        try:
            for msg in messages:
                date = int(msg.get("date", 0))
                text = msg.get("text", "")
                query = """INSERT INTO messages (chat_id, date, text) VALUES (%s, %s, %s)"""
                self.postgres_manager.execute_sql_query(query, (chat_id, date, text))
            self.logger.info(f"{chat_id}: Сообщения добавлены")
        except Exception as e:
            self.logger.error(f"{chat_id}: Ошибка при загрузке сообщений: {e}")
            raise

    def upload_all(self, messages_dict: dict):
        """Обрабатывает все группы: добавляет чаты и сообщения."""
        try:
            self.logger.info("Начата массовая загрузка сообщений в базу")
            self.truncate_messages()  # Удаляем старый набор сообщений
            for chat_id, messages in messages_dict.items():
                self.upload_chat(chat_id)
                self.upload_messages(chat_id, messages)

            self.logger.info("Массовая загрузка завершена")
        except Exception as e:
            self.logger.error(f"Ошибка в upload_all: {e}")
            raise
