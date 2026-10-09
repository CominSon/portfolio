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
            self.cursor.execute(f"SET search_path TO ai_nav_pdf_manager")

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
        """
        Создает необходимые таблицы, если их нет, на основе SQL-файла.
        """
        try:
            self.connect()

            with open(PostgresConfig.SQL_INIT_FILE, "r", encoding="utf-8") as f:
                sql_content = f.read()

            table_queries = [q.strip() for q in sql_content.split(";") if q.strip()]

            for query in table_queries:
                self.cursor.execute(query)
            self.conn.commit()
            self.logger.info("Таблицы PostgreSQL успешно инициализированы")
        except Exception as e:
            self.logger.error(f"Ошибка инициализации таблиц PostgreSQL: {e}")

        finally:
            self.close()
