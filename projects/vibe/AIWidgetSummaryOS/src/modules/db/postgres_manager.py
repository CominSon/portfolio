from __future__ import annotations
import os
import psycopg2
import psycopg2.extras

class PostgresManager:
    """Менеджер БД (фиксированный набор методов)."""

    def __init__(self, logger):
        self.logger = logger
        self.conn = None

    def connect(self):
        dsn = os.getenv("DB_DSN")
        print(dsn)
        if not dsn:
            raise RuntimeError("Не задан DB_DSN в окружении (.env)")
        if psycopg2 is None:
            raise RuntimeError("Не установлен psycopg2. Установите зависимости из requirements.txt")

        self.conn = psycopg2.connect(
            dsn,
            database=os.getenv("DB"),
            connect_timeout=int(os.getenv("DB_CONNECT_TIMEOUT")),
            keepalives=int(os.getenv("DB_KEEPALIVES")),
            keepalives_idle=int(os.getenv("DB_KEEPALIVES_IDLE")),
            keepalives_interval=int(os.getenv("DB_KEEPALIVES_INTERVAL")),
            keepalives_count=int(os.getenv("DB_KEEPALIVES_COUNT")),
        )
        self.conn.autocommit = True
        self.logger.info("Подключение к БД установлено (keepalive включён)")

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
            self.logger.info("Подключение к БД закрыто")

    def execute_sql_query(self, query: str, *args, fetchall: bool = False):
        if self.conn is None:
            raise RuntimeError("Нет подключения к БД. Сначала вызовите connect().")
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            self.logger.debug(f"Выполняю SQL (первые 500 символов): {query[:500]}")
            cur.execute(query, args if args else None)
            if cur.description is None:
                return None
            if fetchall:
                return cur.fetchall()
            else:
                return cur.fetchone()

    def init_tables(self):
        """Создание таблиц метаданных."""
        if self.conn is None:
            raise RuntimeError("Нет подключения к БД. Сначала вызовите connect().")

        schema = os.getenv("AI_META_SCHEMA")
        if not schema:
            raise RuntimeError("Не задан AI_META_SCHEMA в окружении (.env)")

        ddl = f"""
        CREATE TABLE IF NOT EXISTS {schema}.ai_os_ub_prompt_templates ( 
            template_id INT,
            template_name TEXT,
            prompt_json TEXT, -- здесь лежит весь JSON как строка
            is_active BOOL DEFAULT TRUE,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        DISTRIBUTED BY (template_id);

        CREATE TABLE IF NOT EXISTS {schema}.ai_os_ub_widget_meta (
            id_widget NUMERIC,
            group_widget TEXT,
            widget_title TEXT,
            widget_description_short TEXT,
            axis_json TEXT,
            dependencies_json TEXT,
            policy_json TEXT,
            prompt_template_id INT
        )
        DISTRIBUTED BY (id_widget);

        CREATE TABLE IF NOT EXISTS {schema}.ai_os_ub_widget_field_meta (
            id_widget NUMERIC,
            field_name TEXT,
            role TEXT,
            field_description_short TEXT,
            rules_json TEXT,
            priority INT DEFAULT 0
        )
         DISTRIBUTED BY (id_widget);

        CREATE TABLE IF NOT EXISTS {schema}.ai_os_ub_query_templates (
            template_name TEXT,
            sql_template TEXT,
            returns_schema_json TEXT
        )
        DISTRIBUTED randomly;
        
        CREATE TABLE IF NOT EXISTS {schema}.ai_os_ub_results (
            date_update TIMESTAMP NOT NULL,
            group_name TEXT NOT NULL,
            text TEXT NOT NULL
        )
        DISTRIBUTED RANDOMLY;

        """
        with self.conn.cursor() as cur:
            cur.execute(ddl)
        self.logger.info(f"Таблицы метаданных готовы (схема: {schema})")
