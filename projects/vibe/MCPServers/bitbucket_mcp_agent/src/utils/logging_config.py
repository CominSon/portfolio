import logging
import sys
from datetime import datetime


def setup_logging(project_root):
    logger = logging.getLogger("bb_mcp")
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
        log_file = logs_dir / ("bb_mcp_{0}.log".format(datetime.now().strftime("%Y%m%d_%H%M%S")))
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except OSError:
        pass
    return logger
