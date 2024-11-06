import logging
import sys

from logging.handlers import RotatingFileHandler

from aim_helper.app import run
from aim_helper.settings import LOG_FILE

if __name__ == "__main__":
    logging.basicConfig(
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(LOG_FILE, maxBytes=pow(10, 4), mode="w"),
        ]
    )
    run()
