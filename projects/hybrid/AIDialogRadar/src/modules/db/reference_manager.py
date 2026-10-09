from typing import List, Tuple
from src.modules.db.postgres_manager import PostgresManager


class ReferenceManager:
    """Менеджер для работы с эталонными ответами в базе данных."""

    def __init__(self, logger):
        self.logger = logger
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)

    def fetch_reference_data(self) -> Tuple[List[str], List[str]]:
        """Извлекает вопросы и ответы из таблицы reference_answers, которые не помечены как нуждающиеся в проверке."""
        try:
            query = """
                SELECT question, answer 
                FROM reference_answers 
                WHERE needs_review = FALSE
            """
            result = self.postgres_manager.execute_sql_query(query, fetchall=True)
            questions, answers = zip(*result) if result else ([], [])
            self.logger.info(f"Эталонные вопросы и ответы выгружены")
            return list(questions), list(answers)
        except Exception as e:
            self.logger.error(f"Ошибка извлечения эталонных данных: {e}")
            return [], []

    def add_like_by_question(self, question: str):
        """Увеличивает количество лайков на 1 для указанного эталона."""
        try:
            query = """
                UPDATE reference_answers
                SET likes = likes + 1
                WHERE question = %s
            """
            self.postgres_manager.execute_sql_query(query, (question,))
            self.logger.info(f"Лайк добавлен к эталону \"{question}\"")
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении лайка: {e}")

    def add_dislike_by_question(self, question: str):
        """Увеличивает количество дизлайков на 1 и проверяет, нужно ли отметить ответ как требующий пересмотра."""
        try:
            query = """
                UPDATE reference_answers
                SET dislikes = dislikes + 1,
                    needs_review = CASE WHEN dislikes + 1 > likes THEN TRUE ELSE needs_review END
                WHERE question = %s
            """
            self.postgres_manager.execute_sql_query(query, (question, ))
            self.logger.info(f"Дизлайк добавлен к эталону  \"{question}\"")
        except Exception as e:
            self.logger.error(f"Ошибка при добавлении дизлайка: {e}")

    def save_reference_answer(self, question: str, answer: str) -> None:
        """Сохраняет новый эталонный ответ в базу данных."""
        try:
            query = """
                INSERT INTO reference_answers (question, answer)
                VALUES (%s, %s)
            """
            self.postgres_manager.execute_sql_query(query, (question, answer))
            self.logger.info("Новый эталонный ответ добавлен")
        except Exception as e:
            self.logger.error(f"Ошибка при сохранении эталонного ответа: {e}")
