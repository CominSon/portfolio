from typing import Optional
from src.modules.llm.faiss_manager import FaissManager
from src.modules.gigachat.gigachat_manager import GigaChatEmbeddingsManager
from src.modules.llm.llm_config import LLMConfig
from src.modules.db.reference_manager import ReferenceManager


class ReferenceSearchManager:
    """ Поиск ближайших эталонных ответов по эмбендингу вопроса """

    def __init__(self, logger):
        self.logger = logger
        self.embedding_model = GigaChatEmbeddingsManager(logger=self.logger).get_model()
        self.faiss = FaissManager(logger=self.logger, embedding_dim=LLMConfig.EMBEDDING_DIM)
        self.reference_manager: ReferenceManager = ReferenceManager(logger=self.logger)

    def encode_questions(self, questions: list[str]) -> list:
        """Получает эмбендинги для списка вопросов"""
        try:
            return self.embedding_model.embed_documents(questions)
        except Exception as e:
            self.logger.error(f"Ошибка при векторизации вопросов: {e}")
            return []

    def search_reference_answer(self, query_text: str, top_k: int = LLMConfig.TOP_K,
                                sim=LLMConfig.SIMILARITY_DISTANCE) -> list:
        """Находит наиболее подходящий эталонный ответ"""
        try:
            all_results = []
            questions, answers = self.reference_manager.fetch_reference_data()
            if not questions:
                self.logger.info("Эталонная база пуста. Поиск невозможен.")
                return []

            embeddings = self.encode_questions(questions)
            self.faiss.build_index(embeddings, questions)
            # ,
            # 'similarity': results[0][1],
            # 'ref_query': matched_question
            query_embedding = self.embedding_model.embed_query(query_text)
            results = self.faiss.search(query_embedding, top_k=top_k, sim=sim)
            if results:
                matched_question = results[0][0]
                matched_index = questions.index(matched_question)
                all_results.append({
                    'subquery': questions[matched_index],
                    'context': [answers[matched_index]],
                    'similarity': results[0][1],
                    'ref_query': matched_question
                })
                # print(all_results)
                return all_results
        except Exception as e:
            self.logger.error(f"Ошибка поиска эталонного ответа: {e}")
            return []
