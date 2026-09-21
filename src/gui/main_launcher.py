from __future__ import annotations

import logging
import sys

from PyQt6 import QtCore, QtWidgets

from src.gui.csv_to_ifc_app import CsvToIfcWindow
from src.gui.ifc_to_landxml_app import IfcToLandxmlWindow
from src.utils.logging import open_logs_folder, setup_logging


APP_NAME = "Benny Survey Toolkit"


class MainLauncher(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        # Qt does not parent top-level windows. Retain their Python wrappers so
        # launched tools are not collected as soon as these methods return.
        self._child_windows: list[QtWidgets.QWidget] = []
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(400)

        info_label = QtWidgets.QLabel(
            "Choose which part of the workflow you want to run. You can open each tool multiple times."
        )
        info_label.setWordWrap(True)

        csv_button = QtWidgets.QPushButton("CSV → IFC Converter")
        csv_button.clicked.connect(self.launch_csv_app)

        landxml_button = QtWidgets.QPushButton("IFC → LandXML Converter")
        landxml_button.clicked.connect(self.launch_landxml_app)

        logs_button = QtWidgets.QPushButton("Open Logs Folder")
        logs_button.clicked.connect(open_logs_folder)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(info_label)
        layout.addWidget(csv_button)
        layout.addWidget(landxml_button)
        layout.addWidget(logs_button)

        layout.addStretch()
        self.setLayout(layout)

    def launch_csv_app(self) -> None:
        csv_window = CsvToIfcWindow()
        self._show_child_window(csv_window)

    def launch_landxml_app(self) -> None:
        landxml_window = IfcToLandxmlWindow()
        self._show_child_window(landxml_window)

    def _show_child_window(self, window: QtWidgets.QWidget) -> None:
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._child_windows.append(window)
        window.destroyed.connect(lambda _object=None, child=window: self._discard_child_window(child))
        window.show()
        window.activateWindow()
        window.raise_()

    def _discard_child_window(self, window: QtWidgets.QWidget) -> None:
        if window in self._child_windows:
            self._child_windows.remove(window)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    log_file = setup_logging(APP_NAME)
    logging.info("Launcher log file located at %s", log_file)

    launcher = MainLauncher()
    launcher.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
