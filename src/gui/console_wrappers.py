"""Console entry points that keep the optional PyQt6 dependency lazy."""

from __future__ import annotations

import importlib
import sys


def _run_gui(module_name: str) -> int:
    """Run an optional GUI module or explain how to install its dependency."""

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name != "PyQt6":
            raise
        print("This command needs the optional GUI dependency. Install bonsai-topo[gui].", file=sys.stderr)
        return 1
    return int(module.main())


def csv_to_ifc() -> int:
    """Launch the optional CSV-to-IFC GUI."""

    return _run_gui("src.gui.csv_to_ifc_app")


def ifc_to_landxml_gui() -> int:
    """Launch the optional IFC-to-LandXML GUI."""

    return _run_gui("src.gui.ifc_to_landxml_app")


def launcher() -> int:
    """Launch the optional survey-toolkit GUI launcher."""

    return _run_gui("src.gui.main_launcher")
