import os


class GigaChatConfig:
    """Конфигурация необходимая для подключения к Гигачату"""
    CREDENTIALS = os.getenv("GIGACHAT_TOKEN")
    AUTH_URL = os.getenv("GIGACHAT_URL")
    VERIFY_SSL_CERTS = False
    SCOPE = os.getenv("GIGACHAT_SCOPE")
    MODELS = ['Embeddings', 'GigaChat-2-Max']
    PROFANITY_CHECK = False
    TIMEOUT = 300
