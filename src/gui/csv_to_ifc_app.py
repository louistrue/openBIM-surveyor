from __future__ import annotations

import json
import logging
import sys
import traceback
from pathlib import Path
from typing import Optional

from PyQt6 import QtCore, QtWidgets

from src.utils.logging import open_logs_folder, setup_logging
from src.core.converters.csv_to_ifc import create_basic_ifc_with_survey_points


APP_NAME = "Benny CSV to IFC"


class CsvToIfcWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(520)

        self.csv_path_edit = QtWidgets.QLineEdit()
        self.csv_path_edit.setPlaceholderText("Select survey CSV with local coordinates")

        self.csv_browse_button = QtWidgets.QPushButton("Browse…")
        self.csv_browse_button.clicked.connect(self.select_csv_file)

        self.output_path_edit = QtWidgets.QLineEdit()
        self.output_path_edit.setPlaceholderText("Choose IFC output location")

        self.output_browse_button = QtWidgets.QPushButton("Browse…")
        self.output_browse_button.clicked.connect(self.select_output_file)

        self.origin_x_edit = self._create_double_input("Local origin X", 0.0)
        self.origin_y_edit = self._create_double_input("Local origin Y", 0.0)
        self.origin_z_edit = self._create_double_input("Local origin Z", 0.0)

        self.export_button = QtWidgets.QPushButton("Export IFC")
        self.export_button.clicked.connect(self.export_ifc)
        self.export_button.setDefault(True)

        self.open_logs_button = QtWidgets.QPushButton("Open Logs Folder")
        self.open_logs_button.clicked.connect(open_logs_folder)

        self.status_label = QtWidgets.QLabel("Coordinate system: SWEREF99 TM (EPSG:3006)")
        self.status_label.setWordWrap(True)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(self._build_file_row("Input CSV", self.csv_path_edit, self.csv_browse_button))
        layout.addLayout(self._build_file_row("Output IFC", self.output_path_edit, self.output_browse_button))
        layout.addWidget(self._wrap_with_label("Local Origin X", self.origin_x_edit))
        layout.addWidget(self._wrap_with_label("Local Origin Y", self.origin_y_edit))
        layout.addWidget(self._wrap_with_label("Local Origin Z", self.origin_z_edit))

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
        label.setMinimumWidth(85)
        row.addWidget(label)
        row.addWidget(line_edit)
        row.addWidget(browse_button)
        return row

    def _wrap_with_label(self, label_text: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(container)
        layout.addRow(label_text, widget)
        return container

    def _create_double_input(self, placeholder: str, default_value: float) -> QtWidgets.QDoubleSpinBox:
        spin_box = QtWidgets.QDoubleSpinBox()
        spin_box.setRange(-1e8, 1e8)
        spin_box.setDecimals(3)
        spin_box.setValue(default_value)
        spin_box.setAccelerated(True)
        spin_box.setSuffix(" m")
        spin_box.setKeyboardTracking(False)
        spin_box.setToolTip(placeholder)
        return spin_box

    def select_csv_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select survey CSV",
            str(Path.home()),
            "CSV Files (*.csv)",
        )
        if file_path:
            self.csv_path_edit.setText(file_path)
            if not self.output_path_edit.text():
                default_output = Path(file_path).with_suffix(".ifc")
                self.output_path_edit.setText(str(default_output))

    def select_output_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Select IFC output file",
            str(Path.home()),
            "IFC files (*.ifc)",
        )
        if file_path:
            if not file_path.lower().endswith(".ifc"):
                file_path += ".ifc"
            self.output_path_edit.setText(file_path)

    def export_ifc(self) -> None:
        csv_path = self.csv_path_edit.text().strip()
        output_path = self.output_path_edit.text().strip()

        if not csv_path:
            self._show_error("Please select an input CSV file.")
            return
        if not output_path:
            self._show_error("Please choose an output IFC file.")
            return

        csv_file = Path(csv_path)
        if not csv_file.exists():
            self._show_error("The selected CSV file does not exist.")
            return

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        transform_info = {
            "local_origin": {
                "x": self.origin_x_edit.value(),
                "y": self.origin_y_edit.value(),
                "z": self.origin_z_edit.value(),
            },
        }

        self.progress.show()
        self.export_button.setDisabled(True)
        self.status_label.setText("Exporting IFC…")
        QtWidgets.QApplication.processEvents()

        try:
            logging.info("Export start: CSV=%s -> IFC=%s", csv_file, output_file)
            success = create_basic_ifc_with_survey_points(
                csv_file, output_file, transform_info
            )

            if success:
                message = f"IFC created successfully: {output_file}"
                logging.info(message)
                self._show_info(message)
            else:
                logging.error("IFC export returned False")
                self._show_error("IFC export failed. Check the logs for details.")

        except Exception as exc:  # pragma: no cover - user facing exception
            logging.exception("Unhandled error during IFC export: %s", exc)
            formatted_traceback = "".join(traceback.format_exception(*sys.exc_info()))
            self._show_error(
                "An unexpected error occurred. The log file contains more details."
            )
            logging.debug("Traceback: %s", formatted_traceback)
        finally:
            self.progress.hide()
            self.export_button.setEnabled(True)
            self.status_label.setText("Coordinate system: SWEREF99 TM (EPSG:3006)")

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


def load_transform_defaults(transform_file: Optional[Path]) -> Optional[dict]:
    if not transform_file:
        return None
    if not transform_file.exists():
        logging.warning("Transform defaults file not found: %s", transform_file)
        return None
    try:
        with transform_file.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logging.exception("Failed to load transform defaults: %s", exc)
        return None


def get_default_transform_file() -> Optional[Path]:
    """Find the transform defaults file relative to executable or script location."""
    # Try multiple possible locations
    possible_paths = [
        # Relative to current working directory (when run from project root)
        Path("data/processed/client_survey_processed_transform_info.json"),
        # PyInstaller bundled data (when frozen)
        Path(getattr(sys, '_MEIPASS', '.')) / "data" / "processed" / "client_survey_processed_transform_info.json",
        # Relative to executable directory
        Path(sys.executable).parent / "data" / "processed" / "client_survey_processed_transform_info.json",
        # Relative to script directory (development)
        Path(__file__).parent.parent.parent / "data" / "processed" / "client_survey_processed_transform_info.json",
    ]
    
    for path in possible_paths:
        if path.exists():
            logging.info("Found transform defaults at: %s", path)
            return path
    
    logging.warning("No transform defaults file found in any expected location")
    return None


def apply_transform_defaults(window: CsvToIfcWindow, defaults: Optional[dict]) -> None:
    if not defaults:
        return
    local_origin = defaults.get("local_origin")
    if not local_origin:
        return
    window.origin_x_edit.setValue(float(local_origin.get("x", 0.0)))
    window.origin_y_edit.setValue(float(local_origin.get("y", 0.0)))
    window.origin_z_edit.setValue(float(local_origin.get("z", 0.0)))


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)

    log_file = setup_logging(APP_NAME)
    logging.info("Log file located at %s", log_file)
    attach_excepthook(logging.getLogger(__name__))

    window = CsvToIfcWindow()
    default_transform_file = get_default_transform_file()
    default_transform = load_transform_defaults(default_transform_file)
    apply_transform_defaults(window, default_transform)
    window.show()

    return_code = app.exec()
    logging.info("Application exited with code %s", return_code)
    return return_code


if __name__ == "__main__":
    sys.exit(main())


