import os

from csv import DictReader
from time import sleep
from typing import Iterable
from PyQt6.QtCore import (
    QObject,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)

from ..aim_helper.aim_daemon import Job, JobQue, Runnable

TEST_FILE = os.path.join(os.path.split(__file__)[0], "test.csv")


def get_test_data(query):
    query = open(TEST_FILE).readlines()
    return DictReader(query)


class DummyDaemon(QObject):
    """Standin for AimDaemon"""

    started = pyqtSignal()
    finished = pyqtSignal()
    message = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self) -> None:
        super().__init__()
        self.data = []
        self.active = False
        self.jobs = JobQue()
        self.timer = QTimer()
        self.timer.timeout.connect(self.test_work)

        self.timer.start(10000)

    @pyqtSlot(Iterable)
    def do_work(self, data):
        self.data = data
        QThreadPool.globalInstance().start(Runnable(self._do_work))

    @pyqtSlot()
    def test_work(self):
        self.do_work([1, 2, 3, 4, 5])

    def _do_work(self):
        self.started.emit()
        steps = len(self.data)
        for i in range(steps):
            self.message.emit(f"Task {i}")
            self.progress.emit(i, steps - 1)
            sleep(1)
        self.message.emit("Done")
        self.finished.emit()


class DummySession(QObject):
    """Standin for AimSession"""

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.driver = self

    def __getattribute__(self, name):
        return print

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_val, ex_trace):
        return True
