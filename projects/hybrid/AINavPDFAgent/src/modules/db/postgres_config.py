import os


class PostgresConfig:
    """Конфигурация необходимая для подключения к Базе Данных"""
    DBNAME = os.getenv("POSTGRES_DB")
    USER = os.getenv("POSTGRES_USER")
    HOST = os.getenv("POSTGRES_HOST")
    PORT = os.getenv("POSTGRES_PORT")

    # Запрос для первичного создания таблиц
    SQL_INIT_FILE = "resources/init_db.sql"
