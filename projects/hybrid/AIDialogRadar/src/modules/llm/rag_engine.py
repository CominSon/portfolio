import numpy as np
from langchain.vectorstores import faiss

from src.modules.llm.llm_config import LLMConfig
from src.modules.gigachat.gigachat_manager import GigaChatEmbeddingsManager
from src.modules.gigachat.gigachat_manager import GigaChatAPIManager
from src.modules.llm.chat_block_manager import ChatBlockManager
from src.modules.llm.subquestion_generator import SubQuestionGenerator
from src.modules.gigachat.gigachat_promt_loader import GigaChatPromptLoader


class RAGEngine:
    """ Класс, реализующий Retrieval-Augmented Generation (RAG). Использует подзапросы для поиска по FAISS и
    генерации финального ответа."""

    def __init__(self, logger):
        self.logger = logger
        self.embedding_model = GigaChatEmbeddingsManager(logger=self.logger).get_model()
        self.gigachat_api_model = GigaChatAPIManager(logger=self.logger).get_model()
        self.chat_block_manager: ChatBlockManager = ChatBlockManager(logger=self.logger)
        self.sub_generator: SubQuestionGenerator = SubQuestionGenerator(logger=self.logger)
        self.gigachat_prompt_loader: GigaChatPromptLoader = GigaChatPromptLoader(logger=self.logger)

    def search_context_for_question(self, question: str) -> list:
        """
        Ищет релевантные блоки текста по вопросу и его подзапросам.
        """
        try:
            self.logger.info("Сохраняем индексы групп Сбер-чата")
            self.chat_block_manager.build_faiss_index_from_blocks()

            self.logger.info("Формируем подзапросы через GigaChat...")
            subquestions = self.sub_generator.generate_subquestions(question)
            self.logger.info(f"Получено подзапросов: {len(subquestions)}")

            self.logger.info("Загрузка FAISS индекса...")
            if not self.chat_block_manager.get_index():
                self.logger.warning("Индекс FAISS не загружен. Прерывание поиска.")
                return []

            all_results = []
            for sub in subquestions:
                embedding = self.embedding_model.embed_query(sub)
                results = self.chat_block_manager.faiss.search(
                    query_embedding=embedding,
                    top_k=LLMConfig.CHAT_TOP_K,
                    sim=LLMConfig.CHAT_MIN_SIM
                )
                if results:
                    all_results.append({
                        'subquery': sub,
                        'context': results
                    })

            self.logger.info(f"Обнаружено уникальных фрагментов: {len(all_results)}")
            return all_results

        except Exception as e:
            self.logger.error(f"Ошибка в процессе RAG-поиска: {e}")
            return []

    def generate_final_answer(self, user_question: str, contexts: list[str]) -> str:
        """
        Генерация окончательного ответа на основе контекста и вопроса пользователя.
        Ответ формируется на основе подзапросов и найденных блоков контекста.

        :param user_question: Вопрос пользователя.
        :param contexts: Список найденных блоков контекста.
        :return: Финальный сформированный ответ.
        """
        try:
            system_context = self.gigachat_prompt_loader.build_system_context()  # Системные указания
            # Объеденяем все подзапросы и самые подходящие ответы

            context = self.sub_generator.format_context_block(blocks=contexts)
            prompt_template = self.gigachat_prompt_loader.get_prompt('rewrite_final_answer')  # Шаблон промпта для ИИ
            filled_prompt = prompt_template["text"].replace("{question}", user_question).replace("{context}", context)
            full_prompt = f"{system_context} \n\n{filled_prompt}"
            print(full_prompt)
            # Ответ пользователю
            result = self.gigachat_api_model.invoke(full_prompt)

            return result.content
        except Exception as e:
            self.logger.error(f"Ошибка при генерации ответа: {e}")
            return "Не удалось сгенерировать ответ."
