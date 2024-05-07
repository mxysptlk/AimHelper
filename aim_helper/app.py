from __future__ import annotations

import os
import logging
import sys
import traceback

import keyring

from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import QDir, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSystemTrayIcon,
    QToolBar,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QStackedLayout,
    QSizePolicy,
    QAbstractItemView,
)

# from . import resources
from .settings import CONFIG, RESOURCES
from .aim_daemon import AimDaemon


logger = logging.getLogger(__name__)
if CONFIG.debug:
    logger.setLevel(logging.DEBUG)


class SpacerWidget(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class HorizontalContainer(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setLayout(QHBoxLayout())

    def addWidget(self, *args, **kwargs):
        self.layout().addWidget(*args, **kwargs)


class VerticalContainer(QWidget):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setLayout(QVBoxLayout())

    def addWidget(self, *args, **kwargs):
        self.layout().addWidget(*args, **kwargs)


class PasswordChangeDialog(QDialog):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.input = QLineEdit()
        self.confirm = QLineEdit()
        buttons = (
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box = QDialogButtonBox(buttons)
        self.status = QLabel()

        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.button_box.accepted.connect(self.on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QFormLayout()
        layout.addRow(self.status)
        layout.addRow("New password", self.input)
        layout.addRow("Confirm password", self.confirm)
        layout.addRow(self.button_box)

        self.setLayout(layout)

    @Slot()
    def on_accept(self) -> None:
        if self.input.text() != self.confirm.text():
            self.status.setText("Passwords do not match!")
            return
        self.accept()

    def get_password(self) -> str:
        return self.input.text()


class CrashDialog(QDialog):
    def __init__(self, crash_text: str) -> None:
        super().__init__()
        self.setWindowTitle("Error!")
        self.lable = QLabel("Aim-Helper has crashed, click to show detailed report")
        self.text = QPlainTextEdit()
        self.button = QPushButton("Show")

        self.text.hide()
        self.text.setPlainText(crash_text)
        self.button.clicked.connect(self.text.show)

        layout = QVBoxLayout()
        layout.addWidget(self.lable)
        layout.addWidget(self.button)
        layout.addWidget(self.text)

        self.setLayout(layout)


class ConfigWizardWindow(QDialog):
    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Aim-Helper inital config")
        self.help_text = QLabel(
            "Before running Aim-Helper, please enter your NetID Login"
        )
        self.netid = QLineEdit()
        self.password = QLineEdit()
        self.confirm = QLineEdit()
        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        self.status = QLabel()

        self.netid.setText(CONFIG.netid)
        self.button_box.accepted.connect(self.on_accept)
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)

        layout = QFormLayout()
        layout.addRow(self.help_text)
        layout.addRow("NetID", self.netid)
        layout.addRow("Password", self.password)
        layout.addRow("Confirm password", self.confirm)
        layout.addRow(self.status)
        layout.addRow(self.button_box)

        self.setLayout(layout)

    @Slot()
    def on_accept(self) -> None:
        if not self.netid.text():
            self.status.setText("You must enter a NetID")
            return
        if not self.password.text():
            self.status.setText("Password can not be empty")
            return
        if self.password.text() != self.confirm.text():
            self.status.setText("Passwords do not match!")
            return
        CONFIG.netid = self.netid.text()
        keyring.set_password("aim", self.netid.text(), self.password.text())
        self.accept()

    def __enter__(self):
        return self

    def __exit__(self, ex_type, ex_val, ex_trace):
        return True


class DailyAssingnmentsPane(QWidget):
    submit_form = Signal(list)

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.shop_people = QListWidget()
        self.select_all_button = QPushButton("Select All")
        self.submit_button = QPushButton("Create Assignments")

        people = CONFIG.shop_people.copy()
        people.pop("Bill")
        self.shop_people.addItems(people.keys())
        self.shop_people.setSelectionMode(
            QAbstractItemView.SelectionMode.MultiSelection
        )
        self.shop_people.itemSelectionChanged.connect(self._toggle_submit_button)

        self.submit_button.clicked.connect(self.on_submit)
        self.submit_button.setEnabled(False)

        self.select_all_button.clicked.connect(self._toggle_selection)

        container = VerticalContainer()
        container.addWidget(self.select_all_button, 0)
        container.addWidget(self.shop_people)

        layout = QFormLayout()
        layout.addRow(container)
        layout.addRow(self.submit_button)

        self.setLayout(layout)

    @Slot()
    def _toggle_selection(self):
        if self.shop_people.selectedItems():
            self.shop_people.clearSelection()
            self.select_all_button.setText("Select All")
            return
        self.shop_people.selectAll()
        self.select_all_button.setText("Select None")

    @Slot()
    def _toggle_submit_button(self):
        self.submit_button.setEnabled(bool(self.shop_people.selectedItems()))

    @Slot()
    def on_submit(self):
        people = [item.text() for item in self.shop_people.selectedItems()]
        self.submit_form.emit(people)


class NewWorkorderPane(QWidget):
    submit_form = Signal(dict)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self.buildings = QComboBox()
        self.priority = QComboBox()
        self.description = QPlainTextEdit()
        self.assign_yes_no = QCheckBox()
        self.shop_people = QComboBox()
        self.submit_button = QPushButton("Submit")

        self.description.textChanged.connect(self._toggle_submit_button)

        self.priority.addItems(("300 HIGH", "400 ROUTINE", "500 SCHEDULED"))
        self.priority.setCurrentIndex(1)

        self.buildings.addItems(CONFIG.buildings.keys())

        self.assign_yes_no.setMaximumSize(self.assign_yes_no.sizeHint())
        self.assign_yes_no.clicked.connect(self._toggle_combo)

        self.shop_people.setEnabled(self.assign_yes_no.isChecked())
        self.shop_people.addItems(CONFIG.shop_people.keys())

        self.submit_button.setEnabled(False)
        self.submit_button.clicked.connect(self.on_submit)

        assignment_container = HorizontalContainer()
        assignment_container.addWidget(self.assign_yes_no, 0)
        assignment_container.addWidget(self.shop_people)

        layout = QFormLayout()
        layout.addRow("Property", self.buildings)
        layout.addRow("Description", self.description)
        layout.addRow("Priority", self.priority)
        layout.addRow("Assign", assignment_container)
        layout.addRow(self.submit_button)

        self.setLayout(layout)

    @Slot()
    def on_submit(self) -> None:
        person = ""
        if self.assign_yes_no.isChecked():
            person = self.shop_people.currentText()
        workorder = {
            "bldg": CONFIG.buildings[self.buildings.currentText()],
            "description": self.description.toPlainText(),
            "priCode": self.priority.currentText(),
            "shopPerson": person,
        }
        self.submit_form.emit(workorder)

    @Slot()
    def _toggle_submit_button(self):
        self.submit_button.setEnabled(bool(self.description.toPlainText()))

    @Slot()
    def _toggle_combo(self) -> None:
        self.shop_people.setEnabled(self.assign_yes_no.isChecked())


class SettingsPane(QWidget):
    submit_form = Signal(dict)
    message = Signal(str)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self.netid = QLineEdit()
        self.change_password_button = QPushButton("Change Password")
        self.refresh_time = QSpinBox()
        self.ntfy_url = QLineEdit()
        self.ntfy_include_href = QCheckBox("href")
        self.chrome_path = QLineEdit()
        self.chromedriver_path = QLineEdit()
        self.chrome_profile = QLineEdit()
        self.chrome_button = QPushButton("Search")
        self.chrome_profile_button = QPushButton("Search")
        self.chromedriver_button = QPushButton("Search")
        self.debug = QCheckBox("Display chromedriver window")
        self.save_button = QPushButton("Save")

        # Prefill existing config
        self.refresh_time.setValue(int(CONFIG.refresh / 60000))
        self.netid.setText(CONFIG.netid)
        self.ntfy_url.setText(CONFIG.ntfy_url)
        self.ntfy_include_href.setChecked(CONFIG.ntfy_include_href)
        self.chrome_path.setText(CONFIG.chrome_exe)
        self.chrome_profile.setText(CONFIG.chrome_profile)
        self.chromedriver_path.setText(CONFIG.chrome_driver)
        self.debug.setChecked(CONFIG.debug)

        # set tool tips
        self.refresh_time.setToolTip("Time in minuites")
        self.ntfy_include_href.setToolTip("Include AiM link in ntfy notification")
        self.debug.setToolTip("Display chromedriver window")
        # Connect sgnals
        self.change_password_button.clicked.connect(self.get_password)

        self.chrome_button.setMaximumSize(self.chrome_button.sizeHint())
        self.chrome_button.clicked.connect(self._locate_chrome)
        self.chromedriver_button.setMaximumSize(self.chromedriver_button.sizeHint())
        self.chromedriver_button.clicked.connect(self._locate_chromedriver)
        self.chrome_profile_button.setMaximumSize(self.chrome_profile_button.sizeHint())
        self.chrome_profile_button.clicked.connect(self._locate_chrome_profile)

        self.save_button.clicked.connect(self.save)

        # make containers
        ntfy_box = HorizontalContainer()
        ntfy_box.addWidget(self.ntfy_url)
        ntfy_box.addWidget(self.ntfy_include_href)
        chrome_box = HorizontalContainer()
        chrome_box.addWidget(self.chrome_path)
        chrome_box.addWidget(self.chrome_button, 0)

        chromedriver_box = HorizontalContainer()
        chromedriver_box.addWidget(self.chromedriver_path)
        chromedriver_box.addWidget(self.chromedriver_button, 0)

        chrome_profile_box = HorizontalContainer()
        chrome_profile_box.addWidget(self.chrome_profile)
        chrome_profile_box.addWidget(self.chrome_profile_button, 0)

        save_box = HorizontalContainer()
        save_box.addWidget(SpacerWidget())
        save_box.addWidget(self.save_button)
        save_box.addWidget(SpacerWidget())

        scroll_layout = QFormLayout()
        scroll_layout.addRow("NetID", self.netid)
        scroll_layout.addRow(self.change_password_button)
        scroll_layout.addRow(QLabel())
        scroll_layout.addRow("Refresh", self.refresh_time)
        scroll_layout.addRow("ntfy url", ntfy_box)
        scroll_layout.addRow("Chrome Profile", chrome_profile_box)
        scroll_layout.addRow("Chrome exe", chrome_box)
        scroll_layout.addRow("Chrome driver", chromedriver_box)
        scroll_layout.addRow("Debug", self.debug)
        scroll_layout.addRow(SpacerWidget())
        # scroll_layout.addRow(self.save_button)

        settings_container = QWidget()
        settings_container.setLayout(scroll_layout)

        scroll_container = QScrollArea()
        scroll_container.setWidget(settings_container)
        scroll_container.setWidgetResizable(True)

        main_layout = QVBoxLayout()
        main_layout.addWidget(scroll_container)
        main_layout.addWidget(save_box)

        self.setLayout(main_layout)

    @Slot()
    def _locate_chrome_profile(self):
        dialog = QFileDialog(self)
        profile = dialog.getExistingDirectory(
            self, "Locate Chrome profile", QDir.home().path()
        )
        if profile:
            self.chrome_profile.setText(os.path.abspath(profile))

    @Slot()
    def _locate_chrome(self):
        dialog = QFileDialog(self)
        file, _ = dialog.getOpenFileName(self, "Locate Chrome")
        if file:
            self.chrome_path.setText(os.path.abspath(file))

    @Slot()
    def _locate_chromedriver(self):
        dialog = QFileDialog(self)
        file, _ = dialog.getOpenFileName(self, "Locate chromedriver")
        if file:
            self.chromedriver_path.setText(os.path.abspath(file))

    @Slot()
    def get_password(self):
        dialog = PasswordChangeDialog()
        if dialog.exec():
            keyring.set_password("aim", self.netid.text(), dialog.get_password())

    @Slot()
    def save(self):
        data = dict()
        data["netid"] = self.netid.text()
        data["chrome_exe"] = self.chrome_path.text()
        data["chrome_driver"] = self.chromedriver_path.text()
        data["chrome_profile"] = self.chrome_profile.text()
        data["refresh"] = self.refresh_time.value() * 60000
        data["debug"] = self.debug.isChecked()
        data["ntfy_include_href"] = self.ntfy_include_href.isChecked()
        self.submit_form.emit(data)
        self.message.emit("Settings Saved")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.statusbar = self.statusBar()
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        self.setStatusBar(self.statusbar)
        self.statusbar.addPermanentWidget(self.progress_bar)

        # Build toolbar
        self.toolbar = QToolBar("Tools")
        self.toolbar.setMovable(False)
        self._actions = dict()
        menu_entries = {
            "Daily Assignments": self.show_daily_assignments_pane,
            "New Workorder": self.show_new_workorder_pane,
            "Settings": self.show_settings_pane,
            "Quit": self.exit_app,
        }
        for entry, meathod in menu_entries.items():
            self._actions[entry] = QAction(entry, self)
            self._actions[entry].triggered.connect(meathod)
            self.toolbar.addAction(self._actions[entry])
        self.toolbar.insertWidget(self._actions["Quit"], SpacerWidget())
        self.toolbar.insertSeparator(self._actions["Quit"])
        self.addToolBar(self.toolbar)

        # Build tray icon
        # self._normal_icon = QIcon(":icons/aim.png")
        # self._active_icon = QIcon(":icons/aim-active.png")
        self._normal_icon = QIcon(os.path.join(RESOURCES, "aim.png"))
        self._active_icon = QIcon(os.path.join(RESOURCES, "aim-active.png"))
        self._active = False

        self.tray_icon = QSystemTrayIcon()
        self.tray_icon.activated.connect(self.unhide)
        self.tray_icon.setIcon(self._normal_icon)
        tray_menu = QMenu()
        for action in self._actions.values():
            tray_menu.addAction(action)
        tray_menu.insertSeparator(self._actions["Quit"])
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

        self.assignments_pane = DailyAssingnmentsPane(self)
        self.workorder_pane = NewWorkorderPane(self)
        self.settings_pane = SettingsPane(self)

        self.settings_pane.message.connect(self.statusbar.showMessage)

        self.stack = QStackedLayout()
        self.stack.addWidget(self.assignments_pane)
        self.stack.addWidget(self.workorder_pane)
        self.stack.addWidget(self.settings_pane)

        container = QWidget()
        container.setLayout(self.stack)

        self.setCentralWidget(container)
        self.statusbar.showMessage("Ready")

    @Slot()
    def show_daily_assignments_pane(self) -> None:
        self.stack.setCurrentIndex(0)
        self.activateWindow()
        if self.isHidden():
            self.show()

    @Slot()
    def show_new_workorder_pane(self) -> None:
        self.stack.setCurrentIndex(1)
        self.activateWindow()
        if self.isHidden():
            self.show()

    @Slot()
    def show_settings_pane(self) -> None:
        self.stack.setCurrentIndex(2)
        self.activateWindow()
        if self.isHidden():
            self.show()

    @Slot()
    def exit_app(self) -> None:
        self.tray_icon.hide()
        QApplication.quit()

    @Slot(int, int)
    def show_progress(self, completed: int, total: int) -> None:
        self.tray_icon.setToolTip(f"Processing {completed} of {total} jobs.")
        self.progress_bar.show()
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(completed)
        if completed == total:
            self.tray_icon.setToolTip(None)

    @Slot()
    def hide_progress(self):
        self.progress_bar.hide()

    @Slot()
    def unhide(self):
        self.activateWindow()
        self.show()

    @Slot()
    def set_active(self):
        self.tray_icon.setIcon(self._active_icon)

    @Slot()
    def set_inactive(self):
        self.tray_icon.setIcon(self._normal_icon)

    @Slot()
    def toggle_icon(self) -> None:
        if self._active:
            self._active = False
            self.tray_icon.setIcon(self._normal_icon)
        else:
            self.tray_icon.setIcon(self._active_icon)
            self._active = True
        logger.debug(f"MainWindow Active state: {self._active}")

    @Slot(str)
    def show_error(self, message: str) -> None:
        QMessageBox.critical(None, "Error", message)


def first_launch() -> None:
    with ConfigWizardWindow() as wiz:
        if wiz.exec():
            return
    sys.exit()


def run() -> None:
    try:
        app = QApplication(sys.argv)
        app.setQuitOnLastWindowClosed(False)
        if sys.platform == "win32":
            app.setStyle("Fusion")
        app.setWindowIcon(QIcon(os.path.join(RESOURCES, "aim.png")))

        if not CONFIG.netid or not keyring.get_password("aim", CONFIG.netid):
            first_launch()

        daemon = AimDaemon()
        window = MainWindow()

        daemon.processor.started.connect(window.set_active)
        daemon.processor.progress.connect(window.show_progress)
        daemon.processor.message.connect(window.statusbar.showMessage)
        daemon.processor.finished.connect(window.set_inactive)
        daemon.processor.finished.connect(window.progress_bar.hide)
        daemon.processor.error.connect(window.show_error)

        CONFIG.has_changed.connect(daemon.update)

        window.workorder_pane.submit_form.connect(daemon.create_workorder)
        window.assignments_pane.submit_form.connect(daemon.create_daily_assignments)
        window.settings_pane.submit_form.connect(CONFIG.update)
        window.show()

        daemon.start()
        sys.exit(app.exec())
    except Exception:

        m = QMessageBox()
        m.setIcon(QMessageBox.Icon.Critical)
        m.setText("A critical error has occured")
        m.setDetailedText(traceback.format_exc())
        m.exec()


if __name__ == "__main__":
    run()
