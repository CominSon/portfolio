import logging


class LoggerManager:
    def __int__(self):
        pass

    @staticmethod
    def get_logger(log_path: str):
        logger = logging.getLogger("ainavpdfagent")
        if not logger.handlers:
            handler = logging.FileHandler(log_path)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger

