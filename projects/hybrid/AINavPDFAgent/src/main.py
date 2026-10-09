from dotenv import load_dotenv

# Подгружаем ключи, переменные, сертификаты и пароли
load_dotenv()

from modules.common.logger_manager import LoggerManager
from modules.mail.imap_manager import IMAPManager
from modules.llm.llm_agent import LLMAgent
from modules.common.threadpool_manager import ThreadPoolManager
from modules.mail.mail_config import IMAPConfig
from modules.db.postgres_manager import PostgresManager
from modules.core.profiles_orchestrator import ProfileOrchestrator


class Main:
    def __init__(self):
        self.logger = LoggerManager.get_logger("logs/ai_nav_pdf_agent.log")

        # Основные модули
        self.imap_manager: IMAPManager = IMAPManager(logger=self.logger)  # Модуль обработки входящих сообщений
        self.tp: ThreadPoolManager = ThreadPoolManager(logger=self.logger)  # Пул потоков
        self.postgres_manager: PostgresManager = PostgresManager(logger=self.logger)  # Модуль подключения к БД
        self.profiles_orchestrator: ProfileOrchestrator = ProfileOrchestrator(logger=self.logger)
        self.llm_agent: LLMAgent = LLMAgent(orchestrator=self.profiles_orchestrator, logger=self.logger)  # Агент LLM

    def start(self):
        self.logger.info("AiNavPDFAgent запущен")
        self.postgres_manager.init_tables()  # инициализация таблиц (сервер должен быть запущен)
        # Цикл на работу с письмами и агентом
        self.tp.run_thread(self.tp.run_pool,
                           self.imap_manager.reader_fn,
                           self.llm_agent.handler_fn,
                           IMAPConfig.MAIL_CHECK_INTERVAL)

        # Цикл оркестрации профилей
        self.tp.run_thread(self.tp.run_orchestrator, self.profiles_orchestrator.run_loop, 1)

        # Блокирующий цикл
        self.tp.run_block_loop()


if __name__ == '__main__':
    main: Main = Main()
    main.start()
