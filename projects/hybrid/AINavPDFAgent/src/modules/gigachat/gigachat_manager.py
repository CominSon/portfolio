from langchain_gigachat import GigaChat
from langchain_gigachat.embeddings.gigachat import GigaChatEmbeddings
from src.modules.gigachat.gigachat_config import GigaChatConfig


class GigaChatEmbeddingsManager:
    """Менеджер эмбеддингов через GigaChat"""

    def __init__(self, logger):
        self.logger = logger
        self.embedding_model = GigaChatEmbeddings(
            credentials=GigaChatConfig.CREDENTIALS,
            auth_url=GigaChatConfig.AUTH_URL,
            verify_ssl_certs=GigaChatConfig.VERIFY_SSL_CERTS,
            scope=GigaChatConfig.SCOPE,
            model=GigaChatConfig.MODELS[0]  # 'Embeddings'
        )

    def get_model(self):
        try:
            model = self.embedding_model
            return model
        except Exception as e:
            self.logger.error(f"Ошибка Подключения Модели Embeddings: {e}")
            raise


class GigaChatAPIManager:
    """Менеджер LLM-модели GigaChat для генерации текста"""

    def __init__(self, logger):
        self.logger = logger
        self.llm_model = GigaChat(
            credentials=GigaChatConfig.CREDENTIALS,
            auth_url=GigaChatConfig.AUTH_URL,
            verify_ssl_certs=GigaChatConfig.VERIFY_SSL_CERTS,
            scope=GigaChatConfig.SCOPE,
            model=GigaChatConfig.MODELS[1],  # 'GigaChat-2-Max'
            profanity_check=GigaChatConfig.PROFANITY_CHECK,
            timeout=GigaChatConfig.TIMEOUT
        )

    def get_model(self):
        try:
            model = self.llm_model
            return model
        except Exception as e:
            self.logger.error(f"Ошибка Подключения Модели GigaChat-2-Max: {e}")
            raise
