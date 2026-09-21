"""Tests for console entry points that do not import PyQt6 eagerly."""

from __future__ import annotations

from contextlib import redirect_stderr
from io import StringIO
from types import SimpleNamespace
from unittest import mock
import unittest

from src.gui import console_wrappers


class GuiConsoleWrapperTests(unittest.TestCase):
    def test_missing_pyqt_reports_the_optional_extra_for_every_gui_entry_point(self) -> None:
        missing_pyqt = ModuleNotFoundError("No module named 'PyQt6'")
        missing_pyqt.name = "PyQt6"
        for entry_point in (
            console_wrappers.csv_to_ifc,
            console_wrappers.ifc_to_landxml_gui,
            console_wrappers.launcher,
        ):
            stderr = StringIO()
            with self.subTest(entry_point=entry_point.__name__), mock.patch(
                "src.gui.console_wrappers.importlib.import_module", side_effect=missing_pyqt
            ), redirect_stderr(stderr):
                self.assertEqual(entry_point(), 1)
            self.assertIn("bonsai-topo[gui]", stderr.getvalue())

    def test_gui_entry_point_returns_its_lazy_module_exit_code(self) -> None:
        with mock.patch(
            "src.gui.console_wrappers.importlib.import_module",
            return_value=SimpleNamespace(main=lambda: 7),
        ):
            self.assertEqual(console_wrappers.csv_to_ifc(), 7)

    def test_missing_non_pyqt_module_is_not_misreported_as_a_gui_dependency(self) -> None:
        missing_dependency = ModuleNotFoundError("No module named 'ifcopenshell'")
        missing_dependency.name = "ifcopenshell"
        with mock.patch(
            "src.gui.console_wrappers.importlib.import_module", side_effect=missing_dependency
        ), self.assertRaisesRegex(ModuleNotFoundError, "ifcopenshell"):
            console_wrappers.launcher()
