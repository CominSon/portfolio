"""Настройка логирования: файл в logs/ и stderr (не stdout!)."""

import logging
import sys
from datetime import datetime


def setup_logging(project_root):
    # type: (object) -> logging.Logger
    logger = logging.getLogger("gp_mcp")
    logger.setLevel(logging.DEBUG)
    logger.handlers[:] = []

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.INFO)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    try:
        logs_dir = project_root / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = logs_dir / ("gp_mcp_{0}.log".format(timestamp))
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.info("Логирование в файл: %s", log_file)
    except OSError as exc:
        logger.warning("Файловый лог недоступен (%s), только stderr", exc)

    return logger
