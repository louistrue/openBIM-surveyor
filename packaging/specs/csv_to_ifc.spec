# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for CSV to IFC converter app
Build with: pyinstaller --noconfirm --clean --additional-hooks-dir packaging/hooks packaging/specs/csv_to_ifc.spec
"""

import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

block_cipher = None

# Path resolution
spec_dir = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.join(spec_dir, '..', '..')
script_path = os.path.join(project_root, 'src', 'gui', 'csv_to_ifc_app.py')

# Collect ifcopenshell dependencies
hiddenimports = collect_submodules('ifcopenshell')
hiddenimports.extend(['ifcopenshell.geom'])

datas = collect_data_files('ifcopenshell')
# Include coordinate system config
config_path = os.path.join(project_root, 'config', 'coordinate_systems.json')
datas.append((config_path, 'config'))
# Include transform defaults for Benny's coordinates
transform_defaults_path = os.path.join(project_root, 'data', 'processed', 'client_survey_processed_transform_info.json')
datas.append((transform_defaults_path, 'data/processed'))

binaries = collect_dynamic_libs('ifcopenshell')

a = Analysis(
    [script_path],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['packaging/hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt5', 'PyQt5.QtCore', 'PyQt5.QtWidgets', 'PyQt5.QtGui'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Benny CSV to IFC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Benny CSV to IFC',
)
