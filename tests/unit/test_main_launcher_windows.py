"""Lifecycle tests for launcher-owned top-level tool windows."""

from __future__ import annotations

import importlib
import sys
from types import ModuleType, SimpleNamespace
from unittest import mock
import unittest


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self) -> None:
        for callback in tuple(self.callbacks):
            callback()


class _FakeWindow:
    def __init__(self) -> None:
        self.destroyed = _Signal()
        self.attributes = []
        self.shown = False
        self.activated = False
        self.raised = False

    def setAttribute(self, attribute, enabled: bool) -> None:
        self.attributes.append((attribute, enabled))

    def show(self) -> None:
        self.shown = True

    def activateWindow(self) -> None:
        self.activated = True

    def raise_(self) -> None:
        self.raised = True


class MainLauncherWindowTests(unittest.TestCase):
    def test_child_window_is_deleted_on_close_and_discarded_after_destroyed_signal(self) -> None:
        delete_on_close = object()
        qt_core = SimpleNamespace(
            Qt=SimpleNamespace(WidgetAttribute=SimpleNamespace(WA_DeleteOnClose=delete_on_close))
        )
        qt_widgets = SimpleNamespace(QWidget=_FakeWindow)
        pyqt = ModuleType("PyQt6")
        pyqt.QtCore = qt_core
        pyqt.QtWidgets = qt_widgets
        module_names = (
            "src.gui.main_launcher",
            "src.gui.csv_to_ifc_app",
            "src.gui.ifc_to_landxml_app",
        )
        previous = {name: sys.modules.pop(name, None) for name in module_names}
        try:
            with mock.patch.dict(sys.modules, {"PyQt6": pyqt}):
                launcher_module = importlib.import_module("src.gui.main_launcher")
                launcher = object.__new__(launcher_module.MainLauncher)
                launcher._child_windows = []
                child = _FakeWindow()

                launcher._show_child_window(child)

                self.assertEqual(launcher._child_windows, [child])
                self.assertIn((delete_on_close, True), child.attributes)
                self.assertTrue(child.shown and child.activated and child.raised)
                child.destroyed.emit()
                self.assertEqual(launcher._child_windows, [])
        finally:
            for name in module_names:
                sys.modules.pop(name, None)
                if previous[name] is not None:
                    sys.modules[name] = previous[name]


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
