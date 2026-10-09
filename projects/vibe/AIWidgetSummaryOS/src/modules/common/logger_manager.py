import logging
import os
from datetime import datetime
from pathlib import Path

class LoggerManager:
    """Единая точка настройки логирования проекта."""

    def __init__(self, log_dir: str = "src/logs", level: str = "INFO", name: str = "AIWidgetSummary"):
        self.log_dir = log_dir
        self.level = level.upper()
        self.name = name
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)

    def get_logger(self) -> logging.Logger:
        logger = logging.getLogger(self.name)
        if logger.handlers:
            return logger

        logger.setLevel(getattr(logging, self.level, logging.INFO))
        logger.propagate = False

        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(self.log_dir, f"app_{ts}.log")
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        logger.info(f"Логгер инициализирован. Файл лога: {log_path}")
        return logger
