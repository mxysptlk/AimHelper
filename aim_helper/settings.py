from __future__ import annotations

import json
import logging
import os
import sys

from dataclasses import dataclass, asdict, field
from platformdirs import user_config_dir, user_log_dir
from typing import Hashable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(user_config_dir(), "AimHelper")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
COOKIE_FILE = os.path.join(CONFIG_DIR, "cookies.json")
LOG_FILE = os.path.join(user_log_dir(), "aimhelper.log")
os.makedirs(user_log_dir(), exist_ok=True)

RESOURCES = os.path.join(os.path.split(__file__)[0], "res")

if sys.platform == "win32":
    BIN_DIR = os.path.join(HOME, "Programs", "ChromeDriver")
    CHROME_PROFILE = os.path.join(user_config_dir(), "Google", "Chrome", "User Data")
    CHROME_DRIVER_PATH = os.path.join(BIN_DIR, "chromedriver.exe")
    CHROME_EXE_PATH = os.path.join(BIN_DIR, "chrome-win64", "chrome.exe")
else:
    CHROME_DRIVER_PATH = os.popen("which chromedriver").read().strip()
    CHROME_PROFILE = os.path.join(user_config_dir(), "chromium", "Default")
    CHROME_EXE_PATH = ""

SHOP_PEOPLE = {
    "Roland": "819005722",
    "Eric": "846003465",
    "Steve": "847008742",
    "Bill": "850003059",
    "Mehary": "871004976",
}
BUILDINGS = {
    "A Wing": "1221",
    "AA Wing": "1222",
    "B Wing": "1304",
    "BB Wing": "1223",
    "Bioengineering": "4057",
    "C Wing": "1224",
    "CHDD CLINIC": "1219",
    "CHDD South": "1220",
    "Columbia Lift": "3916",
    "D Wing": "1328",
    "E Wing": "1225",
    "F Wing": "1226",
    "G Wing": "1227",
    "H Wing": "1228",
    "Haring Center": "1354",
    "Harris": "1186",
    "Hitchcock": "1324",
    "HSEB": "6534",
    "I Wing": "1300",
    "J Wing": "1174",
    "K Wing": "1173",
    "Portage Bay": "1163",
    "RR Wing": "1175",
    "S. Campus Center": "1308",
    "T Wing": "1168",
}

PRIORITY_CODES = ("300 HIGH", "400 ROUTINE", "500 SCHEDULED")


@dataclass
class Config(QObject):
    netid: str = ""
    ntfy_url: str = "https://ntfy.citisyn.net/17-elec-urgent"
    chrome_exe: str = CHROME_EXE_PATH
    chrome_driver: str = CHROME_DRIVER_PATH
    chrome_profile: str = CHROME_PROFILE
    shop: str = "17 ELECTRICAL"
    shop_people: dict = field(default_factory=lambda: SHOP_PEOPLE)
    refresh: int = 300000
    buildings: dict = field(default_factory=lambda: BUILDINGS)
    debug: bool = True
    ntfy_include_href = False
    has_changed = Signal(str)

    def init(self):
        super().__init__()
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE) as f:
                d = json.load(f)
                self.update(d)
        else:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            open(CONFIG_FILE, "x").close()
            self.save()
        logger.debug(asdict(self))

    def update(self, data: dict) -> None:
        for k, v in data.items():
            d = asdict(self)
            if k in d and d[k] != v:
                self.__setattr__(k, v)
                self.has_changed.emit(k)
        self.save()

    def save(self) -> None:
        with open(CONFIG_FILE, "w") as f:
            json.dump(asdict(self), f, indent=4)


class Config2(QObject):
    "wrapper class for a dict object that can save its contents to a json file"
    has_changed = Signal()
    DEFAULTS = {
        "netid": "wsj3",
        "ntfy url": "https://ntfy.citisyn.net/17-elec-urgent",
        "debug": True,
        "refresh": 300000,
        "chrome location": CHROME_EXE_PATH,
        "chromedriver location": CHROME_DRIVER_PATH,
        "chrome profile": CHROME_PROFILE,
        "shop people": SHOP_PEOPLE,
        "shop": "17 ELECTRICAL",
        "buildings": BUILDINGS,
    }

    def __init__(self, conf: str = CONFIG_FILE) -> None:
        super().__init__()
        self.__config_file = conf
        if os.path.exists(conf):
            with open(conf) as f:
                self.__dict = json.load(f)
            self.__update_dict()

        else:
            self.__dict = self.DEFAULTS
            os.makedirs(CONFIG_DIR, exist_ok=True)
            open(conf, "x").close()
            self.save()

    def __getitem__(self, key: str) -> Hashable:
        return self.__dict.__getitem__(key)

    def __setitem__(self, key: str, val: Hashable) -> None:
        self.__dict.__setitem__(key, val)

    def __delitem__(self, item: str) -> None:
        del self.__dict[item]

    def __contains__(self, item: str) -> None:
        return item in self.__dict

    def __repr__(self) -> str:
        return self.__dict.__repr__()

    def __update_dict(self):
        self.__dict["shop people"] = SHOP_PEOPLE
        self.__dict["buildings"] = BUILDINGS
        for key in self.DEFAULTS:
            if key not in self.__dict:
                self.__dict[key] = self.DEFAULTS[key]
        self.save()

    def update(self, d: dict) -> None:
        self.__dict.update(d)
        self.save()
        self.has_changed.emit()

    def save(self) -> None:
        with open(self.__config_file, "w") as f:
            json.dump(self.__dict, f, indent=4, sort_keys=True)

    def reload(self):
        with open(self.__config_file) as f:
            self.__dict = json.load(f)


CONFIG = Config()
CONFIG.init()
