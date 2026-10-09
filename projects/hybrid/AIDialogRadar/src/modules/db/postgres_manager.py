import psycopg2
from psycopg2 import OperationalError
from src.modules.db.postgres_config import PostgresConfig


class PostgresManager:
    def __init__(self, logger):
        self.logger = logger
        self.conn = None
        self.cursor = None

    def connect(self):
        """Подключаемся к БД Postgres"""
        try:
            self.conn = psycopg2.connect(
                dbname=PostgresConfig.DBNAME,
                user=PostgresConfig.USER,
                host=PostgresConfig.HOST,
                port=PostgresConfig.PORT,
            )
            self.cursor = self.conn.cursor()
            self.logger.info("Успешное подключение к PostgreSQL")
        except OperationalError as e:
            self.logger.error(f"Ошибка подключения к PostgreSQL: {e}")
            raise

    def close(self):
        """Закрываем подключение к БД"""
        try:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()
            self.logger.info("Соединение с PostgreSQL закрыто")
        except Exception as e:
            self.logger.error(f"Ошибка закрытия соединения: {e}")

    def execute_sql_query(self, query, *args, fetchall=False):
        """Выполняем запрос - либо возращаем результат запроса"""
        try:
            self.connect()
            self.cursor.execute(query, *args)
            if fetchall:
                return self.cursor.fetchall()
            else:
                self.conn.commit()
                return None
        except Exception as e:
            self.logger.error(f"Ошибка выполнение SQL-запроса: {e}")
        finally:
            self.close()

    def init_tables(self):
        """Создает необходимые таблицы, если их нет."""
        try:
            self.connect()

            table_queries = [
                """
                CREATE TABLE IF NOT EXISTS chats (
                    id BIGINT PRIMARY KEY
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    date BIGINT,
                    text TEXT,
                    FOREIGN KEY (chat_id) REFERENCES chats(id)
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS reference_answers (
                    id BIGSERIAL PRIMARY KEY,
                    question TEXT,
                    answer TEXT,
                    likes INT DEFAULT 0,
                    dislikes INT DEFAULT 0,
                    needs_review BOOL DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                );
                """
            ]

            for query in table_queries:
                self.cursor.execute(query)
            self.conn.commit()
            self.logger.info("Таблицы PostgreSQL успешно инициализированы")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации таблиц PostgreSQL: {e}")

        finally:
            self.close()
