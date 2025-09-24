#!/usr/bin/env python3
"""
Main survey processing pipeline
Orchestrates the entire workflow from CSV to IFC + LandXML
"""

import os
import sys
import json
import argparse
from pathlib import Path

def load_config():
    """Load coordinate system configuration"""
    config_path = Path("config/coordinate_systems.json")
    with open(config_path, 'r') as f:
        return json.load(f)

def process_csv_data(input_file, output_file, config):
    """Process raw CSV survey data"""
    print(f"Processing {input_file} -> {output_file}")
    
    # Import here to avoid dependency issues if not installed
    try:
        from qgis.qgis_processor import process_survey_csv
        process_survey_csv(input_file, output_file, config)
    except ImportError:
        print("QGIS processor not available, using pandas fallback")
        from .pandas_processor import process_survey_csv_pandas
        process_survey_csv_pandas(input_file, output_file, config)

def import_to_blender(csv_file, ifc_output, config):
    """Import processed CSV to Blender and export IFC"""
    print(f"Importing {csv_file} to Blender -> {ifc_output}")
    
    from blender.survey_importer import import_survey_points
    import_survey_points(csv_file, ifc_output, config)

def export_landxml(ifc_file, landxml_output, config):
    """Export surfaces from IFC to LandXML"""
    print(f"Exporting {ifc_file} -> {landxml_output}")
    
    from export.landxml_exporter import export_to_landxml
    export_to_landxml(ifc_file, landxml_output, config)

def main():
    parser = argparse.ArgumentParser(description='Process survey data through open BIM workflow')
    parser.add_argument('input_csv', help='Input CSV file with survey points')
    parser.add_argument('--output-name', help='Base name for output files', default='survey_project')
    parser.add_argument('--skip-qgis', action='store_true', help='Skip QGIS preprocessing')
    parser.add_argument('--skip-landxml', action='store_true', help='Skip LandXML export')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Set up file paths
    input_path = Path(args.input_csv)
    base_name = args.output_name
    
    processed_csv = Path(f"data/processed/{base_name}.csv")
    ifc_output = Path(f"data/output/{base_name}.ifc")
    landxml_output = Path(f"data/output/{base_name}.xml")
    
    try:
        # Step 1: Process CSV (coordinate transformation, cleaning)
        if not args.skip_qgis:
            process_csv_data(input_path, processed_csv, config)
        else:
            processed_csv = input_path
        
        # Step 2: Import to Blender and create IFC
        import_to_blender(processed_csv, ifc_output, config)
        
        # Step 3: Export LandXML for machine control
        if not args.skip_landxml:
            export_landxml(ifc_output, landxml_output, config)
        
        print(f"\n✅ Processing complete!")
        print(f"📁 IFC file: {ifc_output}")
        if not args.skip_landxml:
            print(f"📁 LandXML file: {landxml_output}")
            
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()