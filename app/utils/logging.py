import logging
from pathlib import Path
from config import LOG_DIR


def get_logger(name='vc', log_file: str = 'latest.log', level='INFO'):
    Path(LOG_DIR).mkdir(exist_ok=True)
    log_path = LOG_DIR / log_file

    logger = logging.getLogger(name)
    logger.setLevel(level.upper())

    if not logger.handlers:
        handler = logging.FileHandler(log_path, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s | %(levelname)-7s | %(name)s | %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
