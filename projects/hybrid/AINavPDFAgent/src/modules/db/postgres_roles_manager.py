from modules.db.postgres_manager import PostgresManager


class PostgresRolesManager:
    def __init__(self, logger):
        self.logger = logger
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)

    def get_user_by_email(self, email: str):
        """Ищем пользователя в таблице ролевой модели"""
        try:
            query = f"""
                SELECT email
                FROM role_model_users
                WHERE lower(email) = lower('{email}')
                LIMIT 1;
                """
            return self.postgres_manager.execute_sql_query(query, fetchall=True)
        except Exception as e:
            self.logger.error(f"[Roles] Ошибка get_user_by_email({email}): {e}")


