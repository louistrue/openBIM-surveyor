"""PyInstaller hook for ifcopenshell to include geometry binaries and data files."""

from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

# Collect all ifcopenshell submodules
hiddenimports = collect_submodules('ifcopenshell')

# Include ifcopenshell.geom explicitly for IFC geometry processing
hiddenimports.extend(['ifcopenshell.geom'])

# Collect data files (schemas, etc.)
datas = collect_data_files('ifcopenshell')

# Collect dynamic libraries (OCE/OpenCASCADE binaries)
binaries = collect_dynamic_libs('ifcopenshell')
