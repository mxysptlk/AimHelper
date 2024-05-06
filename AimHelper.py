import logging
import sys

from logging.handlers import RotatingFileHandler
from platformdirs import user_log_path
from aim_helper.app import run

if __name__ == "__main__":
    logging.basicConfig(
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                user_log_path / "aimhelper.log", maxBytes=pow(10, 6), mode="w"
            ),
        ]
    )
    run()
