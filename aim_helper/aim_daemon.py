from __future__ import annotations

import logging
import requests

from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, List
from PySide6.QtCore import (
    QObject,
    QThreadPool,
    QRunnable,
    QMutex,
    QTimer,
    Signal,
    Slot,
)

from .aim_session import AimSession
from .settings import CONFIG
from .worklist import (
    Workorder,
    get_shop_assignments,
    guess_hrc,
    has_keyword_regex,
    has_no_hrc,
    is_past_due,
    get_workorders,
)

logger = logging.getLogger(__name__)
if CONFIG.debug:
    logger.setLevel(logging.DEBUG)

DISABLE_FETCH = False
MSG = "New Urgent work request(s)"
AIM_URL_TEMPLATE = "https://washington.assetworks.hosting/fmax/screen/PHASE_VIEW?proposal={}&sortCode={}"
INTERVAL = 5 * 60 * 1000
# CANCEL_REGEX = "\\b(an(n)ual.*Maintenance|pm$)\\b"
# HOLD_REGEX = "fire|transfer switch"
URGENT = ("300 HIGH", "200 URGENT", "100 EMERGENCY")


class JobAction(Enum):
    ADD_HRC = 0
    ASSIGN = 1
    CANCEL = 2
    DE_ESCALATE = 3
    HOLD = 4


class Runnable(QRunnable):
    """Helper class to convert Callable to QRunnable"""

    def __init__(self, func: Callable, data: Any = None) -> None:
        super().__init__()
        self._run = func
        self._data = data

    def run(self):
        if self._data:
            self._run(self._data)
            return
        self._run()


class Job(object):
    def __init__(
        self, action: Callable, data: Any, description: str = "Processing..."
    ) -> None:
        self.action = action
        self.data = data
        self.description = description

    def __repr__(self) -> str:
        return f"""
    Job object --
    action: {self.action.__name__}
    data: {self.data}
    description: {self.description}
    """


class JobQue(object):
    """Wrapper class allowing threa-safe access to shared list"""

    def __init__(self) -> None:
        self.__jobs = list()
        self.mutex = QMutex()

    def __bool__(self) -> bool:
        self.mutex.lock()
        r = bool(self.__jobs)
        self.mutex.unlock()
        return r

    def __len__(self) -> int:
        self.mutex.lock()
        r = len(self.__jobs)
        self.mutex.unlock()
        return r

    def __repr__(self) -> str:
        return self.__jobs.__repr__()

    def add_job(self, job) -> None:
        self.mutex.lock()
        self.__jobs.append(job)
        self.mutex.unlock()

    def pop(self) -> Job:
        self.mutex.lock()
        r = self.__jobs.pop(0)
        self.mutex.unlock()
        return r


class AimProcessor(QObject):
    started = Signal()
    finished = Signal()
    progress = Signal(int, int)
    message = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self.jobs = JobQue()
        self.active = False
        self._total_jobs = 0

    def add_job(self, job: Job) -> None:
        QThreadPool.globalInstance().start(Runnable(self.run_one, job))

    @Slot(list)
    def add_jobs(self, jobs: list[Job]) -> None:
        self._total_jobs += len(jobs)
        for job in jobs:
            self.jobs.add_job(job)
        if not self.active:
            QThreadPool.globalInstance().start(Runnable(self.run))

    def run_one(self, job: Job) -> None:
        logger.debug(f"{self.__class__}: run_one")
        logger.debug(job)
        self.active = True
        self.started.emit()
        try:
            with AimSession(netid=CONFIG.netid, debug=CONFIG.debug) as aim:

                aim.progress.connect(self.progress.emit)
                aim.message.connect(self.message.emit)
                job.action(aim, job.data)
        except Exception as e:
            self.error.emit(e)
        self.active = False
        self.message.emit("Done")
        self.finished.emit()

    def run(self) -> None:
        if not self.jobs:
            return
        self.active = True
        completed = 0
        self.started.emit()
        logger.debug(f"{self.__class__}: run: ")

        try:
            with AimSession(netid=CONFIG.netid, debug=CONFIG.debug) as aim:

                while self.jobs:
                    self.progress.emit(completed, self._total_jobs - 1)
                    job = self.jobs.pop()
                    if job.action.__name__ == "make_daily_assignment":
                        logger.debug(job.action.__name__)
                        aim.progress.connect(self.progress.emit)
                    else:
                        self.progress.emit(completed, self._total_jobs - 1)
                    logger.debug(job.description)
                    self.message.emit(job.description)
                    job.action(aim, job.data)
                    if job.action.__name__ == "make_daily_assignment":
                        aim.progress.disconnect()
                    completed += 1
        except Exception as e:
            logger.debug(e)
            self.error.emit(str(e))
        self.active = False
        self._total_jobs = 0
        self.message.emit("Done")
        self.finished.emit()


class AimFetcher(QObject):
    new_jobs = Signal(list)
    new_urgent = Signal(list)
    new_worklist = Signal(list)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)

        self.new_workorders = list()
        self.active_workorders = list()
        self.last_run = datetime.now().astimezone()

    @Slot()
    def fetch(self) -> None:
        QThreadPool.globalInstance().start(self.run)

    def run(self) -> None:

        if DISABLE_FETCH:
            return
        # fetch and sort workorders
        logger.debug(f"{self.__class__}: last_run {self.last_run}")
        logger.debug("Fetching workorders...")
        self.new_workorders = get_workorders("17 Elec New Work")
        self.active_workorders = get_workorders("17 Elec All Active")

        # fetch shop assignments and add to active workorders
        logger.debug("fetching assignments")
        assignments = get_shop_assignments(self.active_workorders)
        for w in self.active_workorders:
            w["shopPerson"] == ""
            for a in assignments:
                if a["proposal"] == w["proposal"] and a["sortCode"] == w["sortCode"]:
                    if a["primaryYn"] == "Y":
                        w["primary"] = a["shopPerson"]
                        logger.debug(
                            f"adding {a['shopPerson']} as primary for {w['proposal']}-{w['sortCode']}"
                        )
                        break
                    if a["primaryYn"] == "N":
                        w["shopPerson"] = a["shopPerson"]
                        logger.debug(
                            f"adding {a['shopPerson']} as shopPerson for {w['proposal']}-{w['sortCode']}"
                        )
                        break

        open_active = list()
        open_active.extend(self.new_workorders)
        open_active.extend(self.active_workorders)
        self.new_worklist.emit(open_active)

        logger.debug("parsing past due...")
        pastdue = [wo for wo in self.active_workorders if is_past_due(wo)]

        logger.debug("parsing pm's...")
        real_pms = [
            wo
            for wo in self.new_workorders
            if has_keyword_regex(wo, CONFIG.hold_regex)
            and wo["priCode"] == "800 PREVENTIVE"
        ]
        fake_pms = [
            wo
            for wo in self.new_workorders
            if has_keyword_regex(wo, CONFIG.cancel_regex) and wo not in real_pms
        ]
        logger.debug("parsing stale...")
        stale_workorders = [
            wo
            for wo in get_workorders("17 Elec HOLD")
            if datetime.today().astimezone() - datetime.fromisoformat(wo["entDate"])
            > timedelta(365)
        ]
        logger.debug("parsing urgent...")
        urgent = [
            wo
            for wo in self.new_workorders
            if datetime.fromisoformat(wo["entDate"]) >= self.last_run
            and wo["priCode"] in URGENT
            and wo not in fake_pms
        ]
        logger.debug("Found:")
        logger.debug(f"{len(fake_pms)} fake pm's")
        logger.debug(f"{len(real_pms)} reals pm's")
        logger.debug(f"{len(pastdue)} past due workorders")
        logger.debug(f"{len(stale_workorders)} stale workorders")
        logger.debug(f"{len(urgent)} urgent workorders")

        cancel = fake_pms + stale_workorders

        # Make job lists
        hold = [make_job(wo, JobAction.HOLD) for wo in real_pms]
        cancel = [make_job(wo, JobAction.CANCEL) for wo in cancel]
        de_escalate = [make_job(wo, JobAction.DE_ESCALATE) for wo in pastdue]

        jobs = hold + cancel + de_escalate

        # emit signals
        if jobs:
            logger.debug(f"{len(jobs)} new jobs found")
            self.new_jobs.emit(jobs)
        if urgent:
            notify_17E_urgent(urgent)

        self.last_run = datetime.now().astimezone()


class AimDaemon(QObject):

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self.processor = AimProcessor()
        self.fetcher = AimFetcher()
        self.timer = QTimer()

        self.timer.timeout.connect(self.fetcher.fetch)
        self.fetcher.new_urgent.connect(notify_17E_urgent)
        self.fetcher.new_jobs.connect(self.processor.add_jobs)

    @Slot()
    def start(self):
        logger.debug("starting daemon")
        self.timer.start(CONFIG.refresh)
        self.fetcher.fetch()

    @Slot()
    def update(self):
        self.timer.setInterval(CONFIG.refresh)

    @Slot(list)
    def create_daily_assignments(self, people: List[str]) -> None:
        msg = "Creating assignments: {}"
        jobs = []
        for person in people:
            jobs.append(Job(make_daily_assignment, person, msg.format(person)))
        self.processor.add_jobs(jobs)

    @Slot(dict)
    def create_workorder(self, workorder: Workorder) -> None:
        self.processor.add_job(
            Job(create_workorder, workorder, "Creating new workorder")
        )

    @Slot()
    def guess_hrcs(self) -> None:
        workorders = []
        for w in self.fetcher.active_workorders:
            if has_no_hrc(w):
                w["HRC"] = guess_hrc(w)
                workorders.append(w)
        self.processor.add_jobs([make_job(w, JobAction.ADD_HRC) for w in workorders])

    @Slot()
    def fix_primary_assignments(self) -> None:
        workorders = [w for w in self.fetcher.active_workorders if w["shopPerson"]]
        self.processor.add_jobs([make_job(w, JobAction.ASSIGN) for w in workorders])

    @Slot(dict)
    def assign_workorder(self, workorder: Workorder) -> None:
        pass

    @Slot(dict)
    def add_hrc_to_workorder(self, workorder: Workorder) -> None:
        pass


def notify_17E_urgent(
    workorders: List[Workorder], ntfy_url: str = CONFIG.ntfy_url
) -> None:
    logger.debug("notify")
    msg = ""
    for wo in workorders:
        url = AIM_URL_TEMPLATE.format(wo["proposal"], wo["sortCode"])
        if CONFIG.ntfy_include_href:
            msg += f"[{wo['proposal']} {wo['sortCode']}]({url}) :\n {wo['description']}\n\n"
        else:
            msg += f"{wo['proposal']} {wo['sortCode']}:\n {wo['description']}\n\n"
        requests.post(
            ntfy_url,
            data=msg.encode(encoding="utf-8"),
            headers={"Title": "New urgent work request(s)", "Markdown": "yes"},
        )


def cancel_workorder(aim: AimSession, workorder: Workorder) -> None:
    aim.change_status(workorder["proposal"], workorder["sortCode"], "CANCEL")


def hold_workorder(aim: AimSession, workorder: Workorder) -> None:
    aim.change_status(workorder["proposal"], workorder["sortCode"], "HOLD")


def de_escalate_workorder(aim: AimSession, workorder: Workorder) -> None:
    aim.deprioritize(workorder["proposal"], workorder["sortCode"])


def create_workorder(aim: AimSession, workorder: Workorder) -> None:
    aim.new_workorder(
        prop=workorder["bldg"],
        desc=workorder["description"],
        priority=workorder["priCode"],
        primary=workorder["shopPerson"],
    )


def make_daily_assignment(aim: AimSession, person: str) -> None:
    aim.make_daily_assignment(person)


def add_hrc(aim: AimSession, workorder: Workorder):
    aim.add_hrc(
        workorder=workorder["proposal"],
        phase=workorder["sortCode"],
        hrc=workorder["HRC"],
    )


def assign_workorder(aim: AimSession, workorder: Workorder):
    aim.reassign(
        workorder=workorder["proposal"],
        phase=workorder["sortCode"],
        shop=CONFIG.shop,
        person=workorder["shopPerson"],
    )
    aim.update_daily_assignment(name=workorder["shopPerson"], wo=workorder["proposal"])


def make_job(workorder: Workorder, action: JobAction) -> Job:
    ACTIONS = {
        JobAction.CANCEL: cancel_workorder,
        JobAction.HOLD: hold_workorder,
        JobAction.DE_ESCALATE: de_escalate_workorder,
        JobAction.ADD_HRC: add_hrc,
        JobAction.ASSIGN: assign_workorder,
    }
    if action not in ACTIONS:
        raise ValueError(f"{action} is not a valid action")
    return Job(
        ACTIONS[action],
        workorder,
        f"{workorder['proposal']} -- {workorder['sortCode']}",
    )
