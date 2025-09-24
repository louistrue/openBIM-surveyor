# Benny's Survey Tools - Packaging Guide

This directory contains the PyInstaller configuration for building standalone Windows executables for Benny's survey workflow.

## Built Applications

Two PyQt6 applications have been packaged:

### 1. CSV to IFC Converter (`Benny CSV to IFC.exe`)
- **Purpose**: Converts survey CSV files to IFC format for use in Bonsai BIM
- **Input**: CSV file with survey points (supports both semicolon and comma delimited)
- **Output**: IFC 4x3 file with georeferenced survey points
- **Features**:
  - Hardcoded coordinate system: SWEREF99 TM (EPSG:3006)
  - Configurable local origin (X, Y, Z coordinates)
  - Automatic CSV format detection
  - Comprehensive error logging

### 2. IFC to LandXML Converter (`Benny IFC to LandXML.exe`)
- **Purpose**: Converts IFC files (after modeling in Bonsai) to LandXML format
- **Input**: IFC file with modeled surfaces and geometry
- **Output**: LandXML 1.2 file compatible with machine control systems
- **Features**:
  - Extracts triangulated surfaces from IFC geometry
  - Maintains coordinate system: SWEREF99 TM (EPSG:3006)
  - Optional point and surface inclusion
  - Comprehensive error logging

## Technical Details

### Dependencies
- **ifcopenshell**: 0.8.3.post2 (IFC file processing)
- **PyQt6**: 6.9.x (GUI framework)
- **numpy**: 2.3.x (numerical operations)
- **scipy**: 1.16.x (triangulation for LandXML)

### Build Configuration
- **PyInstaller**: 6.16.0
- **Build mode**: onedir (for better DLL compatibility)
- **Python version**: 3.13.4
- **Target platform**: Windows 64-bit

### Logging
Both applications feature comprehensive logging:
- **Location**: `logs/` folder next to the executable
- **Format**: Rotating log files (1MB max, 5 backups)
- **Content**: All operations, errors, and debugging information
- **Access**: "Open Logs Folder" button in each application

## Usage for Benny

### Workflow
1. **CSV → IFC**: 
   - Select your survey CSV file
   - Set local origin coordinates (defaults loaded from example data)
   - Export to IFC format
   - Open the IFC in Blender with Bonsai addon

2. **Model in Bonsai**:
   - Use survey points as snap targets
   - Model roads, terraces, utilities as IFC elements
   - Save the enhanced IFC file

3. **IFC → LandXML**:
   - Select the Bonsai-enhanced IFC file
   - Choose output location for LandXML
   - Export for machine control systems

### Error Handling
If something goes wrong:
1. Click "Open Logs Folder" in the application
2. Check the latest log file for detailed error information
3. The log contains full stack traces and operation details

## Build Instructions

### Prerequisites
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r packaging\requirements\csv-to-ifc.txt
pip install -r packaging\requirements\ifc-to-landxml.txt
pip install pyinstaller
```

### Building
```bash
# CSV to IFC app
pyinstaller --noconfirm --clean packaging\specs\csv_to_ifc.spec

# IFC to LandXML app  
pyinstaller --noconfirm --clean packaging\specs\ifc_to_landxml.spec
```

### Output
Executables are built to:
- `dist\Benny CSV to IFC\Benny CSV to IFC.exe`
- `dist\Benny IFC to LandXML\Benny IFC to LandXML.exe`

Each executable is self-contained with all dependencies in the `_internal` folder.

## Deployment

Copy the entire `dist\` folder contents to Benny's machine. No Python installation required.

## Troubleshooting

### Common Issues
1. **Missing DLLs**: Ensure the entire `_internal` folder is copied with the executable
2. **Import errors**: Check the log files for detailed Python tracebacks
3. **File permissions**: Ensure the executable has write permissions for the logs folder

### Log Analysis
Log files contain:
- Application startup/shutdown events
- File processing operations
- Coordinate transformations
- IFC/LandXML generation steps
- Full error tracebacks with line numbers
