import logging
import os
from datetime import datetime

def setup_logger(log_dir="log", log_level=logging.INFO):
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    today = datetime.now().strftime("%Y%m%d")
    log_file = os.path.join(log_dir, f"car_log_{today}.log")
    logger = logging.getLogger("CarControl")
    logger.setLevel(log_level)
    logger.handlers.clear()
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger

logger = setup_logger()
