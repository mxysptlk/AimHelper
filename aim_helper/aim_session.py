from __future__ import annotations

import os
import re
import sys
import time
import keyring
import logging

from datetime import datetime
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    WebDriverException,
    SessionNotCreatedException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.chrome.service import Service
from PySide6.QtCore import QObject, Signal

from .settings import CONFIG

if sys.platform == "win32":
    from subprocess import CREATE_NO_WINDOW
    Service = webdriver.edge.service.Service
    Driver = webdriver.Edge
    Options = webdriver.EdgeOptions
else:
    CREATE_NO_WINDOW = None
    Service = webdriver.chrome.service.Service
    Driver = webdriver.Chrome
    Options = webdriver.ChromeOptions

logger = logging.getLogger(__name__)
if CONFIG.debug:
    logger.setLevel(logging.DEBUG)

DELAY = 0.5

TESTING = True

# URLS
AIM_BASE = "https://washington.assetworks.hosting/fmax/screen/"
AIM_TRAINING = "https://cmms-train.admin.washington.edu/fmax/screen/"
HOME_PAGE = AIM_BASE + "WORKDESK"
AIM_TIMECARD = AIM_BASE + "TIMECARD_VIEW"
WORKORDER_VIEW = AIM_BASE + "WO_VIEW"
PHASE_VIEW = AIM_BASE + "PHASE_VIEW?proposal={}&sortCode={}"
RAPID_TIMECARD_EDIT = AIM_BASE + "RAPID_TIMECARD_EDIT"
DAILY_ASSIGNMENTS = AIM_BASE + "DAILY_ASSIGN_VIEW"
DA_BROWSE = AIM_BASE + "DAILY_ASSIGN_BROWSE?filterName={}%27s%20Daily%20Assignments"


# Element IDs
UID = "weblogin_netid"
PWD = "weblogin_password"
SUBMIT = "submit_button"
TRUST = "trust-browser-button"
REMEMBER = "dampen_choice"

NEW = "mainForm:buttonPanel:new"
DONE = "mainForm:buttonPanel:done"
SAVE = "mainForm:buttonPanel:save"
EDIT = "mainForm:buttonPanel:edit"
YES = "mainForm:buttonControls:yes"
CANCEL = "mainForm:buttonPanel:cancel"
EXECUTE = "mainForm:buttonPanel:executeSearch"
SELECT_ALL = "mainForm:browse:select_all_check"

DA_LOAD_WORKORDERS = "mainForm:DAILY_ASSIGN_EDIT_content:dailyAssignList:link2"
DA_LOAD_PREVIOUS = "mainForm:DAILY_ASSIGN_EDIT_content:dailyAssignList:link1"
DA_DATE = "mainForm:DAILY_ASSIGN_EDIT_content:workDateValue"
DA_OVERHEAD = "mainForm:sideButtonPanel:filterMenu_9"
DA_SHOP_PERSON = "mainForm:DAILY_ASSIGN_EDIT_content:ShopPersonZoom0:ShopPersonZoom"
DA_BROWSE_LATEST = "mainForm:browse:0:ae_daily_assign_e_sched_date"
DA_SEARCH_WO = "mainForm:ae_p_pro_e_proposal"
DA_ERROR = "mainForm:DAILY_ASSIGN_EDIT_content:messages"


TC_ADD_FIRST = (
    "mainForm:TIMECARD_EDIT_content:oldTimecardLineList2:addTimecardItemButton2"
)
TC_ADD_NEXT = "mainForm:buttonPanel:newDetail"
TC_PERSON = "mainForm:TIMECARD_EDIT_content:ShopPersonZoom:level1"
TC_DATE = "mainForm:TIMECARD_EDIT_content:workDateValue"
TC_DECRIPTION = "mainForm:TIMECARD_DETAIL_EDIT_content:ae_p_wka_d_description"
TC_HOURS = "mainForm:TIMECARD_DETAIL_EDIT_content:actHrsValue2"
TC_WORKORDER = "mainForm:TIMECARD_DETAIL_EDIT_content:proposalZoom2:level0"
TC_PHASE = "mainForm:TIMECARD_DETAIL_EDIT_content:proposalZoom2:level1"
TC_ACTION = "mainForm:TIMECARD_DETAIL_EDIT_content:actionTakenZoom2:level1"
TC_LEAVE_CODE = "mainForm:TIMECARD_DETAIL_EDIT_content:leaveCodeZoom2:level0"
TC_LABOR_CODE = "mainForm:TIMECARD_DETAIL_EDIT_content:timeTypeZoom2:level0"
TC_ITEM_NUM = "mainForm:TIMECARD_DETAIL_EDIT_content:ae_p_wka_d_item_no"
TC_ERROR_MSG = "mainForm:TIMECARD_DETAIL_EDIT_content:messages"

RTC_WORK_DATE = "mainForm:RAPID_TIMECARD_EDIT_content:workDate"
RTC_SHOP_PERSON = "mainForm:RAPID_TIMECARD_EDIT_content:shopPersonZoom0:shopPersonZoom"
RTC_LEAVE_CODE = "mainForm:RAPID_TIMECARD_EDIT_content:eaveCodeZoom0:leaveCodeZoom"
RTC_HOURS = "mainForm:RAPID_TIMECARD_EDIT_content:defaultHours"
RTC_SAVE = "mainForm:buttonPanel:save"
RTC_ADD = "mainForm:RAPID_TIMECARD_EDIT_content:addDetail"

WO_DESC = "mainForm:WO_EDIT_content:ae_p_pro_e_description"
WO_REQUESTER = "mainForm:WO_EDIT_content:CDOCZoom:custId"
WO_RQ_BUTTON = "mainForm:WO_EDIT_content:CDOCZoom:custId_button"
WO_TYPE = "mainForm:WO_EDIT_content:WOTCZoom:level0"
WO_CAT = "mainForm:WO_EDIT_content:WOTCZoom:level1"
WO_STATUS = "mainForm:WO_EDIT_content:WOTCSZoom:level2"
WO_PROPERTY = "mainForm:WO_EDIT_content:RFPLZoom:RFPLZoom2"
WO_PROP_ZOOM = "mainForm:WO_EDIT_content:RFPLZoom:RFPLZoom2_button"
WO_ADD_PHASE = "mainForm:WO_EDIT_content:oldPhaseList:addPhaseButton"
WO_NUMBER = "mainForm:WO_VIEW_content:ae_p_pro_e_proposal"
WO_REFERENCE_DATA = "mainForm:sideButtonPanel:moreMenu_1"
WO_REF_SHOP = "mainForm:WO_MORE_EDIT_content:shopShopPerson:level0"
WO_ERRORS = "mainForm:WO_EDIT_content:messages"

PH_DESC = "mainForm:PHASE_EDIT_content:ae_p_phs_e_description"
PH_DESC_V = "mainForm:PHASE_VIEW_content:ae_p_phs_e_description"
PH_SHOP = "mainForm:PHASE_EDIT_content:shopShopPerson:level0"
PH_PRIORITY = "mainForm:PHASE_EDIT_content:priorityCodeZoom:level1"
PH_PRI_ZOOM = "mainForm:PHASE_EDIT_content:primaryShopPerson:level1_button"
PH_WORK_CODE = "mainForm:PHASE_EDIT_content:craftCodeZoom:level1"
PH_WORK_CODE_GRP = "mainForm:PHASE_EDIT_content:craftCodeGroupZoom:level1"
PH_STATUS = "mainForm:PHASE_EDIT_content:phaseStatusZoom:level2"
PH_PRIMARY = "mainForm:PHASE_EDIT_content:primaryShopPerson:level1"
PH_SELECT_SHOP_PEOPLE = "mainForm:PHASE_EDIT_content:shopPeopleBrowse:select_all_check"
PH_REMOVE_SHOP_PEOPLE = "mainForm:PHASE_EDIT_content:shopPeopleBrowse:deleteShopPerson"
PH_LOAD_SHOP_PEOPLE = "mainForm:PHASE_EDIT_content:shopPeopleBrowse:lnkLoadShopPerson"
PH_SHOP_PERSON_CHECK = "mainForm:SHOP_PERSON_BROWSE_content:allPersonsList:{}:check"
PH_SHOP_PERSON_PRIMARY_YN = "/html/body/form[1]/div[4]/div[1]/div/span/table[4]/tbody/tr/td/div/table/tbody/tr/td[4]/span/select/option[1]"
PH_V_STATUS = "mainForm:PHASE_VIEW_content:phaseStatusZoom:level2"
PH_NOTES_LOG = "mainForm:sideButtonPanel:moreMenu_11"
PH_NOTE_TEXT = "mainForm:PHASE_NOTE_ENTRY_EDIT_content:noteField"
PH_EX_DESC_OPEN = "mainForm:sideButtonPanel:moreMenu_0"
PH_EX_DESC_ENTRY = "mainForm:ae_p_phs_e_long_desc"

ACCT_SETUP = "mainForm:sideButtonPanel:moreMenu_2"
ACCT_ADD = "mainForm:WO_ACCT_SETUP_EDIT_content:charge:addChargeAccounts"
ACCT_NEXT = "mainForm:buttonPanel:zoomNext"
ACCT_ID = "mainForm:WO_ACCT_SINGLE_EDIT_content:accountCodeZoom:level0"
ACCT_SUB = "mainForm:WO_ACCT_SINGLE_EDIT_content:subCodeZoom:level1"
ACCT_PERCENT = "mainForm:WO_ACCT_SINGLE_EDIT_content:subPercentValue"

CONNECTION = "DSN=fmax;UID=fmereports;PWD=fmerpts"

WD_CHECKIN = "wd-DropDownCommandButton-56$234380"
WD_CHECKOUT = "wd-DropDownCommandButton-56$234381"
WD_CHECKIN_OK = "abd0c5e699434850b098af4349f3ca7f"
WD_CHECKOUT_OK = "18d0d13631c747b994d882c58ad8275f"


class AimErrorException(Exception):
    pass


class AimSession(QObject):
    """
    Wrapper class for a selenium webdriver object, tailored to
    interacting with the UW work management web app
    """

    message = Signal(str)
    progress = Signal(int, int)

    def __init__(self, *, netid="", debug=TESTING):
        super().__init__()
        if not netid:
            raise ValueError("netid must be provided")
        opt = Options()
        opt.headless = not debug
        opt.add_argument("--remote-debugging-port=9222")
        if CONFIG.chrome_exe:
            opt.binary_location = CONFIG.chrome_exe
        if CONFIG.chrome_profile:
            opt.add_argument(f"user-data-dir={CONFIG.chrome_profile}")
        opt.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.debug = debug
        self.netid = netid
        driver_path = CONFIG.chrome_driver or None
        service = Service(driver_path)
        if CREATE_NO_WINDOW:
            service.creationflags = CREATE_NO_WINDOW
        self.shop = "17 ELECTRICAL"
        logger.info("Initializing webdriver...")
        self.driver = Driver(
            service=service,
            options=opt,
        )
        self.driver.implicitly_wait(20)
        logger.info("Init complete.")

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, ex_type, ex_val, ex_trace):
        self.driver.quit()
        return True

    def __getattr__(self, name):
        return getattr(self.driver, name)

    def login(self):
        "Login to AiM."
        self.driver.get(HOME_PAGE)
        time.sleep(0.1)
        if AIM_BASE not in self.driver.current_url:
            time.sleep(DELAY)
            logger.info("Logging in...")
            password = keyring.get_password("aim", self.netid)
            # clear login fields, in case autofill is enabled
            # for some reason, clear() doesn't work
            self.send_keys_to(UID, [Keys.BACKSPACE] * 1000)
            self.send_keys_to(PWD, [Keys.BACKSPACE] * 1000)
            self.send_keys_to(UID, self.netid)
            self.send_keys_to(PWD, password)
            time.sleep(DELAY)
            self.send_keys_to(PWD, Keys.ENTER)
            while AIM_BASE not in self.driver.current_url:
                time.sleep(DELAY)
                if "Is this your device?" in self.driver.page_source:
                    self.click(TRUST)
            logger.info("login complete.")

    def click(self, item):
        try:
            self.driver.find_element(By.ID, item).click()
        except NoSuchElementException:
            self.driver.find_elements(By.CLASS_NAME, item).click()

    def clear(self, element_id):
        self.driver.find_element(By.ID, element_id).clear()

    def send_keys_to(self, element_id, keys):
        self.driver.find_element(By.ID, element_id).send_keys(keys)

    def deprioritize(
        self, workorder: str, phase: str, priority: str = "500 SCHEDULED"
    ) -> bool:
        """
        Change the priority of a workorder phase
        :param workorder: string -> workorder number
        :param phase: string -> phase
        :param priority: string, defaults to '500 SCHEDULED'
        """
        self.get(PHASE_VIEW.format(workorder, phase))
        try:
            self.click(EDIT)
            self.clear(PH_PRIORITY)
            self.send_keys_to(PH_PRIORITY, priority)
            self.click(SAVE)
            return True
        except NoSuchElementException:
            return False

    def change_status(self, workorder: str, phase: str, status: str) -> bool:
        """
        Change the status of a workorder phase
        :param workorder: string -> workorder number
        :param phase: string -> phase
        :param status: string -> status code
        """
        self.get(PHASE_VIEW.format(workorder, phase))
        try:
            self.click(EDIT)
            self.clear(PH_STATUS)
            self.send_keys_to(PH_STATUS, status)
            if status == "HOLD":
                self.clear(PH_PRIORITY)
                self.send_keys_to(PH_PRIORITY, "500 SCHEDULED")
            self.click(SAVE)
            time.sleep(DELAY)
        except NoSuchElementException:
            pass
        return self.driver.find_element(By.ID, PH_V_STATUS).text == status

    def add_extra_description(self, workorder: str, phase: str, extra: str) -> bool:
        """
        Add extra description to workorder phase
        :param workorder: string -> workorder number
        :param phase: string -> phase
        :param status: extra -> extra description text
        """
        self.get(PHASE_VIEW.format(workorder, phase))
        try:
            self.click(EDIT)
            self.click(PH_EX_DESC_OPEN)
            time.sleep(DELAY)
            extra = self.driver.find_element_by_id(PH_EX_DESC_ENTRY).text + extra
            self.clear(PH_EX_DESC_ENTRY)
            self.send_keys_to(PH_EX_DESC_ENTRY, extra)
            self.click(DONE)
            time.sleep(DELAY)
            self.click(SAVE)
            time.sleep(DELAY)
        except NoSuchElementException:
            return False
        return True

    def _change_code(self, code: str) -> None:
        self.clear(PH_WORK_CODE)
        self.clear(PH_WORK_CODE_GRP)
        self.send_keys_to(PH_WORK_CODE, code)
        self.send_keys_to(PH_WORK_CODE_GRP, "ELECTRICAL")

    def _add_hrc(self, hrc: str) -> None:
        desc = self.driver.find_element(By.ID, PH_DESC).text
        if len(desc) > 198:
            desc = desc[:-8]
        desc += "\n" + hrc
        self.clear(PH_DESC)
        self.send_keys_to(PH_DESC, desc)

    def _guess_hrc(self):
        txt = self.driver.find_element(By.ID, PH_DESC_V).text
        if re.search("\\b(lab|fume(hood)?)\\b", txt, re.IGNORECASE | re.MULTILINE):
            return "HRC107"
        if re.search("\\b(light(s)?)\\b", txt, re.IGNORECASE | re.MULTILINE):
            return "HRC117"
        if re.search("\bb(roof(top)?)\bb", txt, re.IGNORECASE | re.MULTILINE):
            return "HRC109"
        if re.search("lift station", txt, re.IGNORECASE | re.MULTILINE):
            return "HRC113"
        return "HRC110"

    def add_hrc(self, workorder: str, phase: str, hrc: str = "") -> bool:
        self.get(PHASE_VIEW.format(workorder, phase))
        if not hrc:
            hrc = self._guess_hrc()
        elif hrc.isnumeric():
            hrc = f"HRC{hrc}"
        try:
            self.click(EDIT)
            self._add_hrc(hrc)
            self.click(SAVE)
            time.sleep(DELAY)
        except Exception:
            self.click(CANCEL)
            return False
        return True

    def change_code(self, workorder: str, phase: str, code: str) -> bool:
        self.get(PHASE_VIEW.format(workorder, phase))
        try:
            self.click(EDIT)
            self._change_code(code)
            self.click(SAVE)
            time.sleep(DELAY)
        except Exception:
            self.click(CANCEL)
            return False
        return True

    def new_workorder(
        self,
        prop: str,
        desc: str,
        priority: str = "400 ROUTINE",
        primary: str = "",
    ) -> None:
        """
        Create a new workorder in AiM
        :param prop: string -> property number
        :param desc: string -> Description of work
        :param hrc: string -> hazard review code, defaults to ''
        :param priority: string -> priority code, defaults to '400 ROUTINE'
        :param primary: string -> ID number of primary shop person, defaults to ''
        """
        self.__steps = 4 if primary else 3
        self.__completed = 0
        logger.info("Creating new workorder...")
        self.progress.emit(self.__completed, self.__steps)
        self.__completed += 1
        self.message.emit("Creating new workorder...")
        self.get(WORKORDER_VIEW)
        self.click(NEW)
        self.send_keys_to(WO_REQUESTER, self.netid.upper())
        self.click(WO_RQ_BUTTON)

        self.send_keys_to(WO_STATUS, "OPEN")
        self.send_keys_to(WO_TYPE, "MAINTENANCE")
        self.send_keys_to(WO_CAT, "CORRECTIVE")
        self.send_keys_to(WO_DESC, desc)
        self.send_keys_to(WO_PROPERTY, prop)
        self.click(WO_PROP_ZOOM)
        time.sleep(DELAY)
        self.progress.emit(self.__completed, self.__steps)
        self.__completed += 1
        self.message.emit("Setting up account...")
        # Account setup
        self.find_element(By.ID, ACCT_SETUP).click()
        time.sleep(1)
        self.find_element(By.ID, ACCT_ADD).click()
        time.sleep(1)
        self.find_element(By.ID, ACCT_NEXT).click()
        self.find_element(By.ID, ACCT_ID).send_keys("ABSORBED")
        self.find_element(By.ID, ACCT_SUB).send_keys("NONE")
        self.find_element(By.ID, ACCT_PERCENT).send_keys("100")
        self.find_element(By.ID, DONE).click()
        time.sleep(1)
        self.find_element(By.ID, DONE).click()
        # Setup first phase
        self.progress.emit(self.__completed, self.__steps)
        self.__completed += 1
        self.message.emit("Adding first phase...")
        self.click(WO_ADD_PHASE)
        time.sleep(1)
        self.send_keys_to(PH_SHOP, "17 ELECTRICAL")
        self.send_keys_to(PH_WORK_CODE, "ELECTRICAL")
        self.send_keys_to(PH_WORK_CODE_GRP, "ELECTRICAL")
        self.send_keys_to(PH_PRIORITY, priority)

        if primary:
            self.progress.emit(self.__completed, self.__steps)
            self.__completed += 1
            self.send_keys_to(PH_PRIMARY, CONFIG.shop_people[primary])
            self.click(PH_PRI_ZOOM)
            time.sleep(0.1)
            self.clear(PH_STATUS)
            self.send_keys_to(PH_STATUS, "ACTIVE")
        time.sleep(DELAY)
        self.click(DONE)
        self.progress.emit(self.__completed, self.__steps)
        self.message.emit("Done.")
        time.sleep(DELAY)
        self.click(SAVE)
        time.sleep(DELAY)
        error = self.find_element(By.ID, WO_ERRORS).text
        if error:
            self.click(CANCEL)
            time.sleep(DELAY)
            self.click(YES)
            raise AimErrorException("Could not create workorder")
        self.message.emit(self.find_element(By.ID, WO_NUMBER).text)

    def reassign(
        self,
        workorder: str,
        phase: str,
        shop: str = "",
        person: str = "",
        code: str = "",
    ) -> bool:
        # sourcery skip: extract-method
        if not shop:
            shop = "17 MAINTENANCE ELECTRICAL"
        self.get(PHASE_VIEW.format(workorder, phase))
        self.click(EDIT)
        time.sleep(0.1)
        if "Modal Message" in self.driver.title:
            return False
        time.sleep(DELAY)
        try:
            self.click(PH_SELECT_SHOP_PEOPLE)
            self.click(PH_REMOVE_SHOP_PEOPLE)
            time.sleep(0.25)
            if "Modal Message" in self.driver.title:
                self.click(YES)
                time.sleep(0.25)
            try:
                self.clear(PH_SHOP)
                self.send_keys_to(PH_SHOP, shop)
            except WebDriverException:
                pass
            if person:
                self.click(PH_LOAD_SHOP_PEOPLE)
                # Look for the Checkbox associated with the desired person
                for element in self.find_elements(By.CLASS_NAME, "browseRow"):
                    if person in element.text:
                        element.find_element(By.TAG_NAME, "input").click()
                        break
                self.click(DONE)
                time.sleep(0.25)
                self.find_element(By.XPATH, PH_SHOP_PERSON_PRIMARY_YN).click()
            if code:
                self._change_code(code)
            self.click(SAVE)
            return True
        except Exception as e:  # noqa
            self.click(CANCEL)
            print(e)
            return False

    def make_daily_assignment(self, person: str, date: str = "") -> None:
        logger.debug(f"Creating Daily Assignment for {person}")
        self.__completed = 0
        self.__steps = 4

        self.progress.emit(self.__completed, self.__steps)
        self.__completed += 1
        id = CONFIG.shop_people[person]

        self.get(DAILY_ASSIGNMENTS)
        if not date:
            date = datetime.today().strftime("%b %d, %Y")
        time.sleep(DELAY)
        self.click(NEW)
        logger.debug(date)
        time.sleep(DELAY)

        self.send_keys_to(DA_DATE, date)
        self.send_keys_to(DA_SHOP_PERSON, id)

        self._edit_daily_assignment(person)

    def update_daily_assignment(self, name, wo=""):
        self.get(DA_BROWSE.format(name))
        self.click(DA_BROWSE_LATEST)
        self.click(EDIT)
        self._edit_daily_assignment(name, wo)

    def _edit_daily_assignment(self, name, wo=""):
        logger.debug(f"editing assignment for {name}")

        try:
            self.click(DA_LOAD_WORKORDERS)
            time.sleep(0.1)
            self.click(DA_OVERHEAD)
            self.click(EXECUTE)
            time.sleep(0.1)
            self.click(SELECT_ALL)
            time.sleep(0.1)
            self.click(DONE)
            self.progress.emit(self.__completed, self.__steps)
            self.__completed += 1
            self.click(DA_LOAD_PREVIOUS)
            time.sleep(0.1)
            self.progress.emit(self.__completed, self.__steps)
            self.__completed += 1
            self.click(DA_LOAD_WORKORDERS)
            time.sleep(0.1)
            self.progress.emit(self.__completed, self.__steps)
            self.__completed += 1
            if wo:
                self.send_keys_to(DA_SEARCH_WO, wo)
            else:
                for query in self.find_elements(By.CLASS_NAME, "viewMenuLink"):
                    if name in query.text:
                        query.click()
                        break
            self.click(EXECUTE)
            self.click(SELECT_ALL)
            self.click(DONE)
            self.click(SAVE)
            time.sleep(0.1)
            self.click(YES)
            self.progress.emit(self.__completed, self.__steps)
        except NoSuchElementException:
            self.click(CANCEL)
            time.sleep(DELAY)
            self.click(YES)
            raise AimErrorException("Record already exists")


if __name__ == "__main__":
    today = datetime.today()
    aim = AimSession(netid="wsj3")
    aim.login()
