from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from src.utils.logging import open_logs_folder, setup_logging
from src.core.converters.ifc_to_landxml import LandXMLExporter


APP_NAME = "Benny IFC to LandXML"


def load_coordinate_config() -> dict:
    """Load coordinate configuration from multiple possible locations."""
    possible_paths = [
        # Relative to current working directory (when run from project root)
        Path("config/coordinate_systems.json"),
        # PyInstaller bundled data (when frozen)
        Path(getattr(sys, '_MEIPASS', '.')) / "config" / "coordinate_systems.json",
        # Relative to executable directory
        Path(sys.executable).parent / "config" / "coordinate_systems.json",
        # Relative to script directory (development)
        Path(__file__).parent.parent.parent / "config" / "coordinate_systems.json",
    ]
    
    for json_path in possible_paths:
        if json_path.exists():
            try:
                with json_path.open("r", encoding="utf-8") as f:
                    config = json.load(f)
                    logging.info("Loaded coordinate config from: %s", json_path)
                    return config
            except Exception as exc:  # pragma: no cover - user environment issue
                logging.exception("Failed to load coordinate config from %s: %s", json_path, exc)
                continue
    
    logging.warning("No coordinate config found, using SWEREF99 TM defaults")
    # Return default Swedish coordinate system
    return {
        "target_crs": {
            "epsg": 3006,
            "name": "SWEREF99 TM",
            "description": "Swedish national coordinate reference system"
        }
    }


class IfcToLandxmlWindow(QtWidgets.QWidget):
    def __init__(self, coordinate_config: dict) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(520)

        self.coordinate_config = coordinate_config

        self.ifc_path_edit = QtWidgets.QLineEdit()
        self.ifc_path_edit.setPlaceholderText("Select IFC exported from Bonsai")

        self.ifc_browse_button = QtWidgets.QPushButton("Browse…")
        self.ifc_browse_button.clicked.connect(self.select_ifc_file)

        self.output_path_edit = QtWidgets.QLineEdit()
        self.output_path_edit.setPlaceholderText("Choose LandXML output location")

        self.output_browse_button = QtWidgets.QPushButton("Browse…")
        self.output_browse_button.clicked.connect(self.select_output_file)

        self.include_points_checkbox = QtWidgets.QCheckBox("Include points as CgPoints")
        self.include_points_checkbox.setChecked(True)

        self.include_surface_checkbox = QtWidgets.QCheckBox("Include triangulated surface")
        self.include_surface_checkbox.setChecked(True)

        self.export_button = QtWidgets.QPushButton("Export LandXML")
        self.export_button.clicked.connect(self.export_landxml)
        self.export_button.setDefault(True)

        self.open_logs_button = QtWidgets.QPushButton("Open Logs Folder")
        self.open_logs_button.clicked.connect(open_logs_folder)

        epsg = coordinate_config.get("target_crs", {}).get("epsg", "Unknown")
        name = coordinate_config.get("target_crs", {}).get("name", "Local")
        self.status_label = QtWidgets.QLabel(
            f"Coordinate system in output: {name} (EPSG:{epsg})"
        )
        self.status_label.setWordWrap(True)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self._build_file_row("Input IFC", self.ifc_path_edit, self.ifc_browse_button))
        layout.addLayout(
            self._build_file_row("Output LandXML", self.output_path_edit, self.output_browse_button)
        )
        layout.addWidget(self.include_points_checkbox)
        layout.addWidget(self.include_surface_checkbox)

        button_row = QtWidgets.QHBoxLayout()
        button_row.addWidget(self.export_button)
        button_row.addWidget(self.open_logs_button)
        layout.addLayout(button_row)

        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)
        self.setLayout(layout)

    def _build_file_row(
        self,
        label_text: str,
        line_edit: QtWidgets.QLineEdit,
        browse_button: QtWidgets.QPushButton,
    ) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(label_text)
        label.setMinimumWidth(140)
        row.addWidget(label)
        row.addWidget(line_edit)
        row.addWidget(browse_button)
        return row

    def select_ifc_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select IFC file",
            str(Path.home()),
            "IFC Files (*.ifc)",
        )
        if file_path:
            self.ifc_path_edit.setText(file_path)
            if not self.output_path_edit.text():
                default_output = Path(file_path).with_suffix(".xml")
                self.output_path_edit.setText(str(default_output))

    def select_output_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select LandXML output",
            str(Path.home()),
            "LandXML files (*.xml)",
        )
        if file_path:
            if not file_path.lower().endswith(".xml"):
                file_path += ".xml"
            self.output_path_edit.setText(file_path)

    def export_landxml(self) -> None:
        ifc_path = self.ifc_path_edit.text().strip()
        output_path = self.output_path_edit.text().strip()

        if not ifc_path:
            self._show_error("Please select an input IFC file.")
            return
        if not output_path:
            self._show_error("Please choose an output LandXML file.")
            return

        ifc_file = Path(ifc_path)
        if not ifc_file.exists():
            self._show_error("The selected IFC file does not exist.")
            return

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        exporter = LandXMLExporter(self.coordinate_config)

        self.progress.show()
        self.export_button.setDisabled(True)
        self.status_label.setText("Exporting LandXML…")
        QtWidgets.QApplication.processEvents()

        try:
            logging.info("Export start: IFC=%s -> LandXML=%s", ifc_file, output_file)
            success = exporter.export_to_landxml(ifc_file, output_file)

            if success:
                logging.info("LandXML created successfully: %s", output_file)
                self._show_info(f"LandXML created successfully: {output_file}")
            else:
                logging.error("LandXML export returned False")
                self._show_error("LandXML export failed. Check logs for details.")

        except Exception as exc:  # pragma: no cover - user facing exception
            logging.exception("Unhandled error during LandXML export: %s", exc)
            self._show_error(
                "An unexpected error occurred. Please check the log file for details."
            )
        finally:
            self.progress.hide()
            self.export_button.setEnabled(True)
            epsg = self.coordinate_config.get("target_crs", {}).get("epsg", "Unknown")
            name = self.coordinate_config.get("target_crs", {}).get("name", "Local")
            self.status_label.setText(f"Coordinate system in output: {name} (EPSG:{epsg})")

    def _show_error(self, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, "Error", message)

    def _show_info(self, message: str) -> None:
        QtWidgets.QMessageBox.information(self, "Success", message)


def attach_excepthook(logger: logging.Logger) -> None:
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.exception(
            "Uncaught exception: %s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )

        QtWidgets.QMessageBox.critical(
            None,
            "Application Error",
            "An unexpected error occurred. Please check the logs for details.",
        )

    sys.excepthook = handle_exception


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)

    log_file = setup_logging(APP_NAME)
    logging.info("Log file located at %s", log_file)
    attach_excepthook(logging.getLogger(__name__))

    coordinate_config = load_coordinate_config()
    window = IfcToLandxmlWindow(coordinate_config)
    window.show()

    return_code = app.exec()
    logging.info("Application exited with code %s", return_code)
    return return_code


if __name__ == "__main__":
    sys.exit(main())


