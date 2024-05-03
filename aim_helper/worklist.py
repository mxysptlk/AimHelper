import datetime
import json
import logging
import os
import re

from requests import Session
from requests.cookies import cookiejar_from_dict, RequestsCookieJar
from typing import Any, Dict
from urllib.parse import quote

from .aim_session import AimSession
from .settings import CONFIG, COOKIE_FILE

logger = logging.getLogger(__name__)

AIM_BASE = "https://washington.assetworks.hosting/fmax/"
AIM_HOME = AIM_BASE + "screen/WORKDESK"
AIM_API = AIM_BASE + "api/v3/iq-reports/custom-resource?"
AIM_API_PHASE_SEARCH = (
    AIM_API + "filterName={}&screenName=PHASE_SEARCH&value&rowLimit=1000"
)

WO_FIELDS = (
    "proposal",
    "sortCode",
    "description",
    "priCode",
    "entDate",
    "statusCode",
    "bldg",
)

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


class Workorder(dict):
    def __repr__(self) -> str:
        return f"Workorder:\n{json.dumps(self, indent=2)}"


def limit_fields(record: dict, *fields: str) -> Dict[str, Any]:
    """Include only listed fields in a record"""
    return {field: record[field] for field in fields if field in record}


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


def get_workorders(query: str, s: Session = Session()) -> list[Workorder]:
    """Get a list of workorders from AiM using API call

    Args:
        query (str): Name of personal querry
        s (Session, optional): requests.Session object. Defaults to new Session.

    Returns:
        list[Workorder]:
    """
    query = quote(query)

    s.cookies = get_cookies()
    r = s.get(AIM_HOME, allow_redirects=False)
    if r.status_code != 200:
        s.cookies = get_cookies()
    elif r.cookies:
        save_cookies(r.cookies)

    r = s.get(AIM_API_PHASE_SEARCH.format(query))
    if r.status_code != 200:
        return list()
    return [Workorder(record["fields"]) for record in r.json()["ResultSet"]["Results"]]


def is_past_due(record: dict) -> bool:
    if record["priCode"] not in ALLOWABLE_DAYS.keys():
        return False
    created = datetime.datetime.fromisoformat(record["entDate"])
    if (
        datetime.datetime.today().astimezone() - created
        > ALLOWABLE_DAYS[record["priCode"]]
    ):
        return True
    return False


def has_no_hrc(record: dict) -> bool:
    r = re.compile(r"hrc( )?[0-9]{3}$", re.IGNORECASE | re.MULTILINE)
    return not r.search(record["description"])


def has_keyword_regex(record: dict, keyword: str, ignore_case=True) -> bool:
    if ignore_case:
        return re.search(keyword, record["description"], re.IGNORECASE | re.MULTILINE)
    return bool(re.search(keyword, record["description"]))


def guess_hrc(record: dict) -> str:
    txt = record["description"]
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
