# Setup Guide

## Prerequisites

### 1. Python Environment
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Blender + Bonsai
1. Download Blender 3.6+ from https://blender.org
2. Install Bonsai addon:
   - Download from https://github.com/IfcOpenShell/IfcOpenShell
   - Install in Blender: Edit > Preferences > Add-ons > Install
   - Enable "Import-Export: Bonsai"

### 3. QGIS (Optional)
- Download QGIS 3.28+ from https://qgis.org
- Used for advanced coordinate processing
- Can use pandas fallback if not available

## Configuration

### 1. Coordinate Systems
Edit `config/coordinate_systems.json`:

```json
{
  "source_crs": {
    "epsg": 4326,
    "name": "WGS84"
  },
  "target_crs": {
    "epsg": 25832,
    "name": "ETRS89 / UTM zone 32N"
  },
  "local_origin": {
    "x": 500000,
    "y": 5500000,
    "z": 0
  }
}
```

### 2. Input Data Format
CSV files must contain:
- `ID`: Unique point identifier
- `X`, `Y`: Coordinates in source CRS
- `Z`: Elevation (optional)
- `Description`: Point description (optional)
- `Code`: Point classification code (optional)

Example:
```csv
ID,Description,Code,X,Y,Z
1,Corner post,CORNER,6400123.456,5200789.123,145.678
2,Tree,TREE,6400145.789,5200801.456,146.234
```

## Quick Start

### 1. Test with Example Data
```bash
python experiments/prototypes/run_example.py
```

### 2. Process Your Data
```bash
python experiments/prototypes/process_survey.py data/raw/your_survey.csv --output-name your_project
```

### 3. Manual Blender Import
If automated Blender processing fails:
1. Open Blender
2. Install and enable Bonsai addon
3. Run script: `scripts/blender/survey_importer.py`
4. Load your processed CSV file

## Troubleshooting

### Common Issues

**"QGIS not available"**
- Install QGIS or use `--skip-qgis` flag
- Pandas fallback will be used automatically

**"Bonsai addon not found"**
- Install Bonsai addon in Blender
- Enable in Preferences > Add-ons
- Restart Blender

**"Coordinate transformation failed"**
- Check EPSG codes in config
- Verify input coordinates are valid
- Try different target CRS

**"No surfaces found in IFC"**
- Check that terrain surface was created in Blender
- Verify IFC export completed successfully
- Try manual LandXML export

### Performance Tips

- Use local coordinate systems (small numbers)
- Round coordinates to 3 decimal places
- Filter unnecessary survey points
- Process large datasets in batches

## File Structure

```
project/
├── data/
│   ├── raw/           # Original CSV files
│   ├── processed/     # Cleaned CSV files
│   └── output/        # Final IFC and LandXML
├── scripts/
│   ├── process_survey.py    # Main workflow
│   ├── blender/            # Blender automation
│   ├── export/             # LandXML export
│   └── qgis/              # QGIS processing
└── config/
    └── coordinate_systems.json
```