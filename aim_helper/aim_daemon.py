import logging
import requests

from datetime import datetime, timedelta
from typing import Any, Callable, List
from PyQt6.QtCore import (
    QObject,
    QThreadPool,
    QRunnable,
    QMutex,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)

from .aim_session import AimSession
from .settings import CONFIG
from .worklist import Workorder, has_keyword_regex, is_past_due, get_workorders

logger = logging.getLogger(__name__)
if CONFIG.debug:
    logger.setLevel(logging.DEBUG)


MSG = "New Urgent work request(s)"
AIM_URL_TEMPLATE = "https://washington.assetworks.hosting/fmax/screen/PHASE_VIEW?proposal={}&sortCode={}"
INTERVAL = 5 * 60 * 1000
CANCEL_REGEX = "\\b(an(n)ual.*Maintenance|pm)\\b"
HOLD_REGEX = "fire|transfer"
URGENT = ("300 HIGH", "200 URGENT", "100 EMERGENCY")


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
    started = pyqtSignal()
    finished = pyqtSignal()
    progress = pyqtSignal(int, int)
    message = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self.jobs = JobQue()
        self.active = False
        self._total_jobs = 0

    def add_job(self, job: Job) -> None:
        QThreadPool.globalInstance().start(Runnable(self.run_one, job))

    @pyqtSlot(list)
    def add_jobs(self, jobs: list) -> None:
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
                if CONFIG.debug:
                    aim.minimize_window()
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
                if CONFIG.debug:
                    aim.minimize_window()
                while self.jobs:
                    logger.debug(self.jobs)
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
    new_jobs = pyqtSignal(list)
    new_urgent = pyqtSignal(list)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)

        self.new_workorders = list()
        self.active_workorders = list()
        self.last_run = datetime.now().astimezone()

    @pyqtSlot()
    def fetch(self) -> None:
        QThreadPool.globalInstance().start(self.run)

    def run(self) -> None:
        # fetch and sort workorders
        logger.debug(f"{self.__class__}: last_run {self.last_run}")
        logger.debug("Fetching workorders...")
        self.new_workorders = get_workorders("17 Elec New Work")
        self.active_workorders = get_workorders("17 Elec All Active")

        logger.debug("parsing past due...")
        pastdue = [wo for wo in self.active_workorders if is_past_due(wo)]

        logger.debug("parsing pm's...")
        real_pms = [
            wo for wo in self.new_workorders if has_keyword_regex(wo, HOLD_REGEX)
        ]
        fake_pms = [
            wo
            for wo in self.new_workorders
            if has_keyword_regex(wo, CANCEL_REGEX) and wo not in real_pms
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
            if datetime.fromisoformat(wo["entDate"]) > self.last_run
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
        hold = [make_job(wo, "hold") for wo in real_pms]
        cancel = [make_job(wo, "cancel") for wo in cancel]
        de_escalate = [make_job(wo, "de-escalate") for wo in pastdue]

        jobs = hold + cancel + de_escalate

        # emit signals
        if jobs:
            logger.debug(f"{len(jobs)} new jobs found")
            logger.debug(jobs)
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

    @pyqtSlot()
    def start(self):
        logger.debug("starting daemon")
        self.timer.start(CONFIG.refresh)
        self.fetcher.fetch()

    @pyqtSlot()
    def update(self):
        self.timer.setInterval(CONFIG.refresh)

    @pyqtSlot(list)
    def create_daily_assignments(self, people: List[str]) -> None:
        msg = "Creating assignments: {}"
        jobs = []
        for person in people:
            jobs.append(Job(make_daily_assignment, person, msg.format(person)))
        self.processor.add_jobs(jobs)

    @pyqtSlot(dict)
    def create_workorder(self, workorder: Workorder) -> None:
        self.processor.add_job(
            Job(create_workorder, workorder, "Creating new workorder")
        )


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
    logger.debug(person)
    aim.make_daily_assignment(person)


def make_job(workorder: Workorder, action: str) -> Job:
    ACTIONS = {
        "cancel": cancel_workorder,
        "hold": hold_workorder,
        "de-escalate": de_escalate_workorder,
    }
    if action not in ACTIONS:
        raise ValueError(f"{action} is not a valid action")
    return Job(
        ACTIONS[action],
        workorder,
        f"{workorder['proposal']} -- {workorder['sortCode']}",
    )
