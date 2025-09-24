from __future__ import annotations

import logging
import sys

from PyQt6 import QtWidgets

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.gui.app_logging import open_logs_folder, setup_logging
from scripts.gui.csv_to_ifc_app import CsvToIfcWindow
from scripts.gui.ifc_to_landxml_app import IfcToLandxmlWindow


APP_NAME = "Benny Survey Toolkit"


class MainLauncher(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
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
        csv_window.show()
        csv_window.activateWindow()
        csv_window.raise_()

    def launch_landxml_app(self) -> None:
        landxml_window = IfcToLandxmlWindow({"target_crs": {"epsg": 3006, "name": "SWEREF99 TM"}})
        landxml_window.show()
        landxml_window.activateWindow()
        landxml_window.raise_()


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    log_file = setup_logging(APP_NAME)
    logging.info("Launcher log file located at %s", log_file)

    launcher = MainLauncher()
    launcher.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())


