import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def log_info(message: str) -> None:
    logging.info(message)

def log_error(message: str) -> None:
    logging.error(message)

def log_warning(message: str) -> None:
    logging.warning(message)
