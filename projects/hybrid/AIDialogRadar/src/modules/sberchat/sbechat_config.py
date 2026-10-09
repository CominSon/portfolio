import os


class SberChatConfig:
    """Конфигурация необходимая для подключения к Сберчату"""
    ENDPOINT = os.getenv("SBERCHAT_ENDPOINT")  # Адрес сервера
    TOKEN = os.getenv("SBERCHAT_TOKEN")  # Токен бота Сберчата
    IS_SECURE = True  # Защищенное соединение для локальной разработки
    GROUP_IDS = [1263451699, 1172109189, 2027452944]  # Здесь список id чатов (которые доступны для анализа)
