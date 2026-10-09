from src.modules.gigachat.gigachat_manager import GigaChatEmbeddingsManager
from src.modules.db.reference_manager import ReferenceManager
from src.modules.llm.reference_search_manager import ReferenceSearchManager
from src.modules.llm.rag_engine import RAGEngine
from src.modules.llm.llm_config import LLMConfig


class DialogOrchestrator:
    def __init__(self, logger):
        self.logger = logger

        # Инициализация модулей
        self.embedding_model = GigaChatEmbeddingsManager(logger=self.logger)
        self.reference_manager = ReferenceManager(logger=self.logger)
        self.reference_search_manager = ReferenceSearchManager(logger=self.logger)
        self.rag_engine: RAGEngine = RAGEngine(logger=self.logger)

    def get_reference_answer(self, user_question: str) -> list:
        """
        Пытаемся найти эталонный ответ по вопросу пользователя.
        Возвращает ответ или None, если нет подходящего результата.
        """
        # Выполняем поиск ближайшего эталона
        best_result = self.reference_search_manager.search_reference_answer(user_question)

        if best_result:
            self.logger.info("Найден релевантный эталонный ответ.")
            return best_result
        else:
            self.logger.info("Нет подходящего эталонного ответа.")
            return []

    def handle_question(self, user_question: str):
        """Обрабатываем все варианты работы с вопросом"""
        self.logger.info(f"Получен запрос: {user_question}")

        # 1. Сначала пробуем найти ответ в эталонной базе
        pre_final_answer = self.get_reference_answer(user_question)
        if pre_final_answer:
            is_reference = True
            similarity = pre_final_answer[0]["similarity"]
            ref_question = pre_final_answer[0]["ref_query"]
        # 2. Если нет, пробуем RAG
        else:
            pre_final_answer = self.rag_engine.search_context_for_question(question=user_question)
            is_reference = False
            similarity = 0
            ref_question = ""
        # 3. Прокручиваем ответ(ы) через модель GigaChat
        final_answer = self.rag_engine.generate_final_answer(user_question, pre_final_answer)

        # 4. Возвращаем ответ пользователю (дополнительно возвращаем тег и сходимость)
        # return final_answer

        return {
            'answer': final_answer,
            'is_reference': is_reference,
            'similarity': similarity,
            'ref_question': ref_question
        }

    def handle_like(self, user_question, answer, is_reference, similarity, ref_question):
        """Обрабатываем кнопку Like"""
        if is_reference and float(similarity) >= LLMConfig.SIMILARITY_DISTANCE_REF:
            self.reference_manager.add_like_by_question(ref_question)
            self.logger.info("Добавлен Like к эталонному вопросу")
            return 'like_incremented'
        else:
            self.reference_manager.save_reference_answer(user_question, answer)
            self.logger.info("Добавлен новый эталонный вопрос")
            return 'reference_added'

    def handle_dislike(self, user_question, is_reference, similarity, ref_question):
        """Обрабатываем кнопку DisLike"""
        if is_reference and float(similarity) >= LLMConfig.SIMILARITY_DISTANCE_REF:
            self.reference_manager.add_dislike_by_question(ref_question)
            self.logger.info("Добавлен DisLike к эталонному вопросу")
        pre_final_answer = self.rag_engine.search_context_for_question(question=user_question)
        final_answer = self.rag_engine.generate_final_answer(user_question, pre_final_answer)
        return {
            'answer': final_answer,
            'is_reference': False,
            'similarity': 0,
            'ref_question': ""
        }