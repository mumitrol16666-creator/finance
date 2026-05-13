from loguru import logger
import sys

def setup_logging(debug: bool):
    logger.remove()
    logger.add(sys.stdout, level="DEBUG" if debug else "INFO", backtrace=debug, diagnose=debug)
    return logger
