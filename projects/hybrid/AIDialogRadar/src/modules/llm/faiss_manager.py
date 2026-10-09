import os
import pickle
import faiss
import numpy as np


class FaissManager:
    def __init__(self, logger, embedding_dim: int):
        """
        Инициализация менеджера FAISS.
        :param embedding_dim: Размерность эмбеддингов (обычно 1024 для GigaChat)
        """
        self.logger = logger
        self.embedding_dim = embedding_dim
        # self.index = faiss.IndexFlatL2(embedding_dim)
        self.index = faiss.IndexFlatIP(embedding_dim)
        self.texts = []

    def build_index(self, embeddings: list[np.ndarray], texts: list[str]):
        """
        Построение индекса по эмбеддингам и сохранение соответствующих текстов.
        :param embeddings: Список numpy-массивов эмбеддингов
        :param texts: Список текстов, соответствующих эмбеддингам
        """
        try:
            if len(embeddings) != len(texts):
                raise ValueError("Количество эмбеддингов и текстов должно совпадать")

            vectors = np.vstack(embeddings).astype('float32')
            faiss.normalize_L2(vectors)
            self.index.add(vectors)
            self.texts = texts
        except Exception as e:
            self.logger.error(f"Ошибка при построении индексов по эмбеддингам: {e}")
            raise

    def search(self, query_embedding: np.ndarray, top_k, sim) -> list:
        """
        Поиск ближайших текстов по эмбеддингу запроса.
        :param sim: Порог схождения по дистанции
        :param query_embedding: Эмбеддинг запроса (numpy-массив)
        :param top_k: Количество ближайших результатов
        :return: Список найденных текстов
        """
        try:
            query_embedding = np.array([query_embedding]).astype('float32')
            faiss.normalize_L2(query_embedding)
            distances, indices = self.index.search(query_embedding, top_k)
            if len(self.texts) == 0:
                return []
            results = []
            for i, dist in zip(indices[0], distances[0]):
                if i != -1 and dist >= sim and i < len(self.texts):
                    results.append([self.texts[i], dist])
            return results
        except Exception as e:
            self.logger.error(f"Ошибка поиска текста по эмбеддингам: {e}")
            raise

    def save_index(self, path: str):
        """Сохраняет FAISS-индекс и тексты на диск"""
        try:
            faiss.write_index(self.index, path)
            text_path = f"{path}.txt.pkl"
            with open(text_path, "wb") as f:
                pickle.dump(self.texts, f)
            self.logger.info(f"FAISS-индекс сохранен в файл: {path}")
        except Exception as e:
            self.logger.error(f"Ошибка сохранения FAISS-индекса {e}")
            raise

    def load_index(self, path: str):
        """Загружает FAISS-индекс и тексты с диска."""
        try:
            if not os.path.exists(path):
                raise FileNotFoundError(f"Файл индекса не найден: {path}")
            self.index = faiss.read_index(path)
            text_path = path + ".txt.pkl"
            if os.path.exists(text_path):
                with open(text_path, "rb") as f:
                    self.texts = pickle.load(f)
            else:
                self.texts = []
            self.logger.info(f"FAISS-индекс загружен из файла: {path}")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка загрузки FAISS-индекса: {e}")
            return False
