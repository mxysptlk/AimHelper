from __future__ import annotations

import datetime
import json
import logging
import logging.handlers
import os
import re

from requests import Session
from requests.cookies import cookiejar_from_dict, RequestsCookieJar
from typing import Any, Dict
from urllib.parse import quote

from .aim_session import AimSession
from .settings import CONFIG, COOKIE_FILE

logger = logging.getLogger(__name__)
if CONFIG.debug:
    logger.setLevel(logging.DEBUG)

AIM_BASE = "https://washington.assetworks.hosting/fmax/"
AIM_HOME = AIM_BASE + "screen/WORKDESK"
AIM_API = AIM_BASE + "api/v3/iq-reports/custom-resource?"
AIM_API_PHASE_SEARCH = (
    AIM_API + "filterName={}&screenName=PHASE_SEARCH&value&rowLimit=1000"
)
AIM_API_SHOP_ASSIGNMET_SEARCH = (
    AIM_API + "tableName=AePProS&proposal={}&value&rowLimit=10000"
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

    def __getitem__(self, key: Any) -> Any:
        if key not in self.keys():
            return ""
        return super().__getitem__(key)

    def __repr__(self) -> str:
        return f"Workorder:\n{json.dumps(self, indent=2)}"


def limit_fields(workorder: Workorder, *fields: str) -> Dict[str, Any]:
    """Include only listed fields in a workorder"""
    return {field: workorder[field] for field in fields}


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
    if r.cookies:
        s.cookies = r.cookies
        save_cookies(r.cookies)
    logger.debug(f"Fetching {AIM_API_PHASE_SEARCH.format(query)}")
    r = s.get(AIM_API_PHASE_SEARCH.format(query))
    logger.debug(f"Respose code:{r.status_code}")
    if r.status_code != 200:
        return list()
    workorders = [
        Workorder(**workorder["fields"])
        for workorder in r.json()["ResultSet"]["Results"]
    ]
    return workorders


def is_past_due(workorder: Workorder) -> bool:
    if workorder["priCode"] not in ALLOWABLE_DAYS.keys():
        return False
    created = datetime.datetime.fromisoformat(workorder["entDate"])
    if (
        datetime.datetime.today().astimezone() - created
        > ALLOWABLE_DAYS[workorder["priCode"]]
    ):
        return True
    return False


def has_no_hrc(workorder: Workorder) -> bool:
    r = re.compile(r"hrc( )?[0-9]{3}$", re.IGNORECASE | re.MULTILINE)
    return not r.search(workorder["description"])


def has_keyword_regex(workorder: Workorder, keyword: str, ignore_case=True) -> bool:
    if ignore_case:
        return re.search(
            keyword, workorder["description"], re.IGNORECASE | re.MULTILINE
        )
    return bool(re.search(keyword, workorder["description"]))


def guess_hrc(workorder: Workorder) -> str:
    txt = workorder["description"]
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


def get_shop_assignments(
    workorders: list[Workorder], s: Session = Session()
) -> list[dict]:
    s.cookies = get_cookies()
    r = s.get(AIM_HOME, allow_redirects=False)
    if r.cookies:
        s.cookies = r.cookies
        save_cookies(r.cookies)

    proposals = ",".join([w["proposal"] for w in workorders])
    logger.debug(f"Fetching {AIM_API_SHOP_ASSIGNMET_SEARCH.format(proposals)}")

    r = s.get(AIM_API_SHOP_ASSIGNMET_SEARCH.format(proposals))
    logger.debug(f"Respose code:{r.status_code}")

    if r.status_code != 200:
        return list()
    return [p["fields"] for p in r.json()["ResultSet"]["Results"]]

