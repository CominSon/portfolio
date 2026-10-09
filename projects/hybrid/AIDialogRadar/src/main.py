from dotenv import load_dotenv

load_dotenv()  # Подгружаем ключи, переменные, сертификаты и пароли

from src.modules.db.postgres_manager import PostgresManager
from src.modules.sberchat.sberchat_manager import SberChatManager
from src.modules.common.logger_manager import LoggerManager
from src.modules.web.flask_app import FlaskApp


class Main:
    def __init__(self):
        self.logger = LoggerManager.get_logger("logs/project.log")

        # Основные модули
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)  # Модуль подключения к БД
        self.sberchat_manager: SberChatManager = SberChatManager(logger=self.logger)  # Модуль работы с SDK SberChat
        self.flask_app: FlaskApp = FlaskApp(logger=self.logger)  # Модуль запуска веб-приложения

    def start(self):
        self.logger.info("AIDialogRadar запущен")

        self.postgres_manager.init_tables()  # Инициализируем таблицы postgres (если их нет)
        self.sberchat_manager.safe_chat_in_base()  # Считваем данные из Сбер-чата и записываем в БД

        # Запуск веб. морды
        self.flask_app.run()

        self.logger.info("AIDialogRadar закрыт")


if __name__ == "__main__":
    main: Main = Main()
    main.start()
