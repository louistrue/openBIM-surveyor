"""
QGIS-based CSV processing for coordinate transformation and data cleaning
This script can be run within QGIS Python console or as standalone with QGIS Python API
"""

import csv
import json
from pathlib import Path

# Try to import QGIS modules (will fail if not in QGIS environment)
try:
    from qgis.core import (
        QgsApplication, QgsVectorLayer, QgsProject, QgsCoordinateReferenceSystem,
        QgsCoordinateTransform, QgsFeature, QgsGeometry, QgsPointXY,
        QgsVectorFileWriter, QgsWkbTypes
    )
    QGIS_AVAILABLE = True
except ImportError:
    QGIS_AVAILABLE = False
    print("QGIS not available - using fallback pandas processor")

def process_survey_csv(input_file, output_file, config):
    """Process survey CSV with QGIS coordinate transformation"""
    if not QGIS_AVAILABLE:
        raise ImportError("QGIS not available")
    
    print(f"Processing {input_file} with QGIS")
    
    # Initialize QGIS application (if not already running)
    if not QgsApplication.instance():
        qgs = QgsApplication([], False)
        qgs.initQgis()
    
    # Set up coordinate systems
    source_crs = QgsCoordinateReferenceSystem(f"EPSG:{config['source_crs']['epsg']}")
    target_crs = QgsCoordinateReferenceSystem(f"EPSG:{config['target_crs']['epsg']}")
    
    # Create coordinate transform
    transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
    
    # Read input CSV
    points = []
    with open(input_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        
        for row in reader:
            try:
                # Get coordinates
                x = float(row['X'])
                y = float(row['Y'])
                z = float(row.get('Z', 0))
                
                # Transform coordinates
                point = QgsPointXY(x, y)
                transformed_point = transform.transform(point)
                
                # Apply local origin offset
                local_origin = config.get('local_origin', {'x': 0, 'y': 0, 'z': 0})
                final_x = transformed_point.x() - local_origin['x']
                final_y = transformed_point.y() - local_origin['y']
                final_z = z - local_origin['z']
                
                # Round to specified precision
                precision = config.get('precision', {}).get('decimal_places', 3)
                final_x = round(final_x, precision)
                final_y = round(final_y, precision)
                final_z = round(final_z, precision)
                
                # Update row with transformed coordinates
                row['X'] = final_x
                row['Y'] = final_y
                row['Z'] = final_z
                
                points.append(row)
                
            except (ValueError, KeyError) as e:
                print(f"Skipping invalid row: {row} - Error: {e}")
                continue
    
    # Write processed CSV
    if points:
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(points)
        
        print(f"✅ Processed {len(points)} points -> {output_file}")
        print(f"Coordinate transformation: EPSG:{config['source_crs']['epsg']} -> EPSG:{config['target_crs']['epsg']}")
    else:
        print("❌ No valid points found")

def create_qgis_project_template(output_path, config):
    """Create a QGIS project template for manual processing"""
    if not QGIS_AVAILABLE:
        print("QGIS not available - cannot create project template")
        return
    
    # This would create a .qgs project file with:
    # - Proper CRS settings
    # - Layer styling for survey points
    # - Processing toolbox configurations
    
    print(f"QGIS project template functionality would be implemented here")
    print(f"Template would be saved to: {output_path}")

if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) >= 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        
        # Load config
        config_path = Path("../../config/coordinate_systems.json")
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        process_survey_csv(input_file, output_file, config)