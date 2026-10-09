import json
import uuid
from datetime import datetime

from modules.core.pofiles_config import ProfilesConfig
from modules.db.postgres_manager import PostgresManager


class PostgresProfileManager:
    def __init__(self, logger):
        self.logger = logger
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)
        self.profiles_config: ProfilesConfig = ProfilesConfig()

    def get_active_tasks(self):
        """
        Возвращает список всех активных задач из таблицы browser_tasks_monitor.
        """
        try:
            query = """
                SELECT process_id, task_type, payload_json, customer_email,
                       profile_name, started_at
                FROM browser_tasks_monitor
                WHERE status = 'active'
            """
            return self.postgres_manager.execute_sql_query(query, fetchall=True)
        except Exception as e:
            self.logger.error(f"[PostgreSQL] Ошибка проверки активных задач: {e}")

    def reserve_profile(self, task_type: str, payload: dict, customer_email: str):
        """
        Резервирует свободный профиль. Если все заняты — возвращает None.
        :param task_type: тип задачи (например, 'pdf_generation')
        :param payload: словарь с параметрами задачи (будет сохранён в JSON)
        :param customer_email: email заказчика
        :param profiles: список допустимых профилей
        """
        try:
            active = self.get_active_tasks()
            used_profiles = [row[4] for row in active]
            free_profiles = [p for p in self.profiles_config.list_profiles() if p not in used_profiles]
            if not free_profiles:
                self.logger.warning("[PostgreSQL] Нет свободных профилей для новой задачи")
                return None

            chosen_profile = free_profiles[0]
            print(chosen_profile)
            process_id = str(uuid.uuid4())

            query = """
                INSERT INTO browser_tasks_monitor (process_id, task_type, payload_json, customer_email, profile_name, status)
                VALUES (%s, %s, %s, %s, %s, 'active')
            """
            params = (process_id,
                      task_type,
                      json.dumps(payload, ensure_ascii=False),
                      customer_email,
                      chosen_profile)
            self.postgres_manager.execute_sql_query(query, params)

            self.logger.info(f"[PostgreSQL] Профиль {chosen_profile} зарезервирован, process_id={process_id}")
            return {"process_id": process_id, "profile_name": chosen_profile}
        except Exception as e:
            self.logger.error(f"[PostgreSQL] Ошибка резервирования профиля: {e}")

    def update_task_status(self, process_id: str, status: str):
        """
        Обновляет статус задачи (done или failed) и проставляет время завершения.
        """
        try:
            if status not in ("done", "failed"):
                raise ValueError("Статус должен быть 'done' или 'failed'")

            query = """
                UPDATE browser_tasks_monitor
                SET status = %s,
                    finished_at = %s
                WHERE process_id = %s
            """
            params = (status, datetime.now(), process_id)
            self.postgres_manager.execute_sql_query(query, params)
            self.logger.info(f"[ProfileManager] Задача {process_id} завершена со статусом {status}")
        except Exception as e:
            self.logger.error(f"[PostgreSQL] Ошибка обновления статуса задачи: {e}")
