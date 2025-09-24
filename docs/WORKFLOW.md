# Workflow Documentation

## Overview

This workflow replaces proprietary Topocad with an open-source pipeline that maintains the same functionality while adding BIM compliance and automation.

## Detailed Steps

### 1. Field Data Collection

**Input**: CSV files from GNSS rover or excavator logs

**Required columns**:
- `ID`: Unique point identifier
- `X`, `Y`: Coordinates (any EPSG system)
- `Z`: Elevation (optional but recommended)
- `Description`: Human-readable description
- `Code`: Classification code for grouping

**Example codes**:
- `CORNER`: Property corners
- `TREE`: Vegetation
- `BUILDING`: Structure corners
- `ROAD`: Road edges
- `UTILITY`: Utility infrastructure
- `BENCHMARK`: Survey control points

### 2. QGIS Preprocessing

**Purpose**: Clean data and transform coordinates

**Process**:
1. Import CSV into QGIS or use pandas fallback
2. Reproject from GPS coordinates (EPSG:4326) to local CRS
3. Apply site-centered origin to keep coordinates small
4. Filter unnecessary columns
5. Round to specified precision (typically 3 decimals)
6. Export cleaned CSV

**Benefits**:
- Avoids numeric precision issues with large coordinates
- Standardizes data format
- Removes survey artifacts

### 3. Blender + Bonsai Import

**Purpose**: Create 3D BIM model with survey data

**Process**:
1. Run Python script in Blender
2. Import cleaned CSV points
3. Create `IfcAnnotation` objects with `PredefinedType = SURVEY`
4. Attach custom property set `SurveyData{ID, Description, Code}`
5. Organize points into Collections by Code
6. Generate basic terrain surface using Delaunay triangulation

**IFC Structure**:
```
IfcProject
├── IfcSite
│   ├── Survey Points (IfcAnnotation)
│   │   ├── Collection: CORNER
│   │   ├── Collection: TREE
│   │   └── Collection: ROAD
│   └── Terrain (IfcGeographicElement)
```

### 4. Design Modeling

**Purpose**: Add designed elements using survey points as reference

**Elements**:
- **Terrain/Earthworks** → `IfcGeographicElement` with TIN tessellation
- **Excavation bottoms** → `IfcEarthworksElement`
- **Roads/Sidewalks** → `IfcPavement` with `IfcCourse` layers
- **Utilities** → `IfcPipeSegment`, `IfcCableSegment`

**Workflow**:
1. Snap to survey points for accurate positioning
2. Model surfaces using Blender's mesh tools
3. Assign appropriate IFC classes via Bonsai
4. Maintain georeferencing with `IfcProjectedCRS`

### 5. Dual Export

#### IFC 4x3 Export
**Purpose**: Master BIM file for coordination

**Contains**:
- All survey points with metadata
- Terrain surfaces
- Designed elements (roads, utilities, etc.)
- Proper georeferencing
- Material properties
- Relationships between elements

#### LandXML Export
**Purpose**: Machine control for excavators

**Contains**:
- Triangulated surfaces (TINs)
- Coordinate system information
- Surface definitions compatible with machine control systems

**Format**:
```xml
<LandXML version="1.2">
  <CoordinateSystem epsgCode="25832"/>
  <Surfaces>
    <Surface name="Terrain">
      <Definition surfType="TIN">
        <Pnts>
          <P id="1">123.456 789.123 145.678</P>
        </Pnts>
        <Faces>
          <F>1 2 3</F>
        </Faces>
      </Definition>
    </Surface>
  </Surfaces>
</LandXML>
```

## Comparison with Topocad

| Aspect | Topocad | Open Workflow |
|--------|---------|---------------|
| **Data Format** | Proprietary | Open standards (IFC, LandXML) |
| **BIM Integration** | Limited IFC support | Full IFC 4x3 compliance |
| **Automation** | Manual workflows | Python scripted |
| **Coordinate Handling** | Rigid, numeric issues | Flexible, local CRS |
| **Metadata** | Black box | Fully preserved |
| **Vendor Lock-in** | Yes | No |
| **Cost** | License required | Open source |

## Quality Control

### Data Validation
- Check coordinate ranges after transformation
- Verify all required fields are present
- Validate point classifications
- Ensure proper CRS transformation

### Visual Inspection
- Review point distribution in Blender
- Check terrain surface quality
- Verify IFC structure in Bonsai
- Test LandXML in machine control software

### Export Verification
- Confirm IFC file opens in other BIM software
- Test LandXML compatibility with excavator systems
- Validate coordinate system information
- Check surface continuity

## Automation Opportunities

### Batch Processing
```bash
# Process multiple surveys
for file in data/raw/*.csv; do
    python experiments/prototypes/process_survey.py "$file"
done
```

### Scheduled Updates
- Monitor field data folder for new CSV files
- Automatically process and update BIM model
- Generate reports on survey progress

### Integration Points
- Connect to survey equipment APIs
- Link with project management systems
- Export to cloud-based BIM platforms
- Interface with machine control systems

## Best Practices

### Data Management
- Use consistent naming conventions
- Maintain version control for processed data
- Archive raw survey data
- Document coordinate system choices

### Modeling Standards
- Follow local BIM standards (e.g., ISO 19650)
- Use consistent IFC classifications
- Maintain proper object relationships
- Include sufficient metadata

### Quality Assurance
- Regular validation of coordinate transformations
- Cross-check with existing survey data
- Verify machine control compatibility
- Test workflow with sample data