import os
from dotenv import load_dotenv

from modules.common.logger_manager import LoggerManager
from modules.db.postgres_manager import PostgresManager
from modules.llm.fake_llm_manager import FakeLLMManager
from modules.llm.gigachat_llm_manager import GigaChatLLMManager
from modules.core.diagnostics import Diagnostics

def main():
    load_dotenv()

    logger = LoggerManager(log_dir="src/logs", level=os.getenv("LOG_LEVEL", "INFO"), name="AIWidgetSummary").get_logger()

    provider = os.getenv("LLM_PROVIDER", "fake").strip().lower()
    llm = GigaChatLLMManager(provider="gigachat", logger=logger) if provider == "gigachat" else FakeLLMManager(provider="fake", logger=logger)

    pg = PostgresManager(logger)
    pg.connect()

    diag = Diagnostics(pg_manager=pg, llm_manager=llm, logger=logger)

    logger.info(f"Проверка БД: {diag.check_db()}")
    logger.info(f"Проверка os_ub_nav: {diag.check_os_ub_nav_access()}")
    logger.info(f"Проверка LLM ({provider}): {diag.check_llm()}")

    pg.close()

if __name__ == "__main__":
    main()
