import datetime
import json
import logging
import os
import re

from csv import DictReader
from requests import Session
from requests.cookies import cookiejar_from_dict, RequestsCookieJar
from urllib.parse import quote

from .aim_session import AimSession
from .settings import CONFIG, COOKIE_FILE

logger = logging.getLogger(__name__)

AIM_BASE = "https://washington.assetworks.hosting/fmax/"
AIM_HOME = AIM_BASE + "screen/WORKDESK"
AIM_PHASE_SEARCH = AIM_BASE + "screen/PHASE_BROWSE?filterName={filter}"
AIM_TEST = AIM_PHASE_SEARCH.format(filter="Impact Review")
AIM_CSV = AIM_BASE + "csv?fmaxScreenName=PHASE_BROWSE"

HOME = os.path.expanduser("~")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

ALLOWABLE_DAYS = {
    "200 URGENT": datetime.timedelta(1),
    "300 HIGH": datetime.timedelta(7),
    "400 ROUTINE": datetime.timedelta(25),
}


def _get_new_cookies(netid: str = CONFIG.netid) -> dict:
    cookies = {}
    logger.debug("fetching new cookies")
    with AimSession(netid=netid) as aim:
        if CONFIG.debug:
            aim.minimize_window()
        for cookie in aim.get_cookies():
            cookies[cookie["name"]] = cookie["value"]
    return cookies


def get_cookies() -> RequestsCookieJar:
    cookies = {}
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE) as f:
            cookies = json.load(f)
        s = Session()
        r = s.get(AIM_HOME, cookies=cookies, allow_redirects=False)
        if r.status_code == 200:
            return cookiejar_from_dict(cookies)

    cookies = _get_new_cookies()
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f)
    return cookiejar_from_dict(cookies)


def save_cookies(cookies: RequestsCookieJar):
    cookie_dict = {k: v for k, v in cookies.items()}
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookie_dict, f)


def get_workorders(query: str, s: Session = None) -> DictReader:
    """Retrieve a workorder list from AiM

    Args:
        query (str): The name of an AiM personal query
        s (Session, optional): an existing requests.Session object.

    Returns:
        DictReader: An iterable of dict objects. Element names match columns
        shown in querry
    """
    query = quote(query)
    if not s:
        s = Session()
        s.cookies = get_cookies()
    r = s.get(AIM_HOME, allow_redirects=False)
    if r.status_code != 200:
        s.cookies = get_cookies()
    elif r.cookies:
        save_cookies(r.cookies)

    r = s.get(AIM_PHASE_SEARCH.format(filter=query))
    r = s.get(AIM_CSV)
    return DictReader(r.text.splitlines())


def is_past_due(record: dict) -> bool:
    if record["Priority"] not in ALLOWABLE_DAYS.keys():
        return False
    created = datetime.datetime.fromisoformat(record["Date Created"])
    if datetime.datetime.today() - created > ALLOWABLE_DAYS[record["Priority"]]:
        return True
    return False


def has_no_hrc(record: dict) -> bool:
    r = re.compile(r"hrc( )?[0-9]{3}$", re.IGNORECASE | re.MULTILINE)
    return not r.search(record["Description"])


def has_keyword_regex(record: dict, keyword: str, ignore_case=True) -> bool:
    if ignore_case:
        return re.search(keyword, record["Description"], re.IGNORECASE | re.MULTILINE)
    return re.search(keyword, record["Description"])


def guess_hrc(record: dict) -> str:
    txt = record["Description"]
    if re.search(
        r"\b(animal(s)?|primate|lab|fume(hood)?)\b", txt, re.IGNORECASE | re.MULTILINE
    ):
        return "107"
    if re.search(r"\b(light(s)?)\b", txt, re.IGNORECASE | re.MULTILINE):
        return "117"
    if re.search(r"\b(roof(top)?)\b", txt, re.IGNORECASE | re.MULTILINE):
        return "109"
    if re.search("lift station", txt, re.IGNORECASE | re.MULTILINE):
        return "113"
    return "110"
