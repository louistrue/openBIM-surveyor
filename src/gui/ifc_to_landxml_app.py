from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path

from PyQt6 import QtWidgets

from src.utils.logging import open_logs_folder, setup_logging
from src.core.converters.ifc_to_landxml import (
    LandXmlExportError,
    export_ifc_terrain_to_landxml,
)


APP_NAME = "Benny IFC to LandXML"


class IfcToLandxmlWindow(QtWidgets.QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumWidth(520)

        self.ifc_path_edit = QtWidgets.QLineEdit()
        self.ifc_path_edit.setPlaceholderText("Select IFC exported from Bonsai")

        self.ifc_browse_button = QtWidgets.QPushButton("Browse…")
        self.ifc_browse_button.clicked.connect(self.select_ifc_file)

        self.output_path_edit = QtWidgets.QLineEdit()
        self.output_path_edit.setPlaceholderText("Choose LandXML output location")

        self.output_browse_button = QtWidgets.QPushButton("Browse…")
        self.output_browse_button.clicked.connect(self.select_output_file)

        self.terrain_global_id_edit = QtWidgets.QLineEdit()
        self.terrain_global_id_edit.setPlaceholderText(
            "Required: IfcGeographicElement GlobalId (not STEP id or name)"
        )

        self.export_button = QtWidgets.QPushButton("Export LandXML")
        self.export_button.clicked.connect(self.export_landxml)
        self.export_button.setDefault(True)

        self.open_logs_button = QtWidgets.QPushButton("Open Logs Folder")
        self.open_logs_button.clicked.connect(open_logs_folder)

        self.status_label = QtWidgets.QLabel(
            "Output CRS and map units are read from the selected IFC IfcMapConversion; no default CRS is used."
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
        layout.addLayout(self._build_text_row("Terrain GlobalId", self.terrain_global_id_edit))

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

    def _build_text_row(self, label_text: str, line_edit: QtWidgets.QLineEdit) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        label = QtWidgets.QLabel(label_text)
        label.setMinimumWidth(140)
        row.addWidget(label)
        row.addWidget(line_edit)
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
        terrain_global_id = self.terrain_global_id_edit.text().strip()

        if not ifc_path:
            self._show_error("Please select an input IFC file.")
            return
        if not output_path:
            self._show_error("Please choose an output LandXML file.")
            return
        if not terrain_global_id:
            self._show_error("Please provide the selected terrain's IfcGeographicElement GlobalId.")
            return

        ifc_file = Path(ifc_path)
        if not ifc_file.exists():
            self._show_error("The selected IFC file does not exist.")
            return

        output_file = Path(output_path)
        self.progress.show()
        self.export_button.setDisabled(True)
        self.status_label.setText("Exporting LandXML…")
        QtWidgets.QApplication.processEvents()

        try:
            logging.info("Export start: IFC=%s terrain=%s -> LandXML=%s", ifc_file, terrain_global_id, output_file)
            mesh = export_ifc_terrain_to_landxml(
                ifc_file,
                output_file,
                terrain_global_id=terrain_global_id,
            )
            logging.info("LandXML created successfully: %s", output_file)
            self._show_info(
                f"LandXML created successfully: {output_file}\n"
                f"Terrain: {mesh.name}; points: {len(mesh.vertices_enz)}; faces: {len(mesh.faces)}."
            )

        except LandXmlExportError as exc:  # pragma: no cover - user facing exception
            logging.error("LandXML export rejected IFC: %s", exc)
            self._show_error(str(exc))
        except Exception as exc:  # pragma: no cover - user facing exception
            logging.exception("Unhandled error during LandXML export: %s", exc)
            self._show_error("An unexpected error occurred. Please check the log file for details.")
        finally:
            self.progress.hide()
            self.export_button.setEnabled(True)
            self.status_label.setText(
                "Output CRS and map units are read from the selected IFC IfcMapConversion; no default CRS is used."
            )

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

    window = IfcToLandxmlWindow()
    window.show()

    return_code = app.exec()
    logging.info("Application exited with code %s", return_code)
    return return_code


if __name__ == "__main__":
    sys.exit(main())

