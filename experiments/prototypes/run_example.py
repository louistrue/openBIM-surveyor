#!/usr/bin/env python3
"""
Example script to run the complete workflow with sample data
"""

import sys
import os
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

from process_survey import main as process_main
from pandas_processor import validate_csv_format, process_survey_csv_pandas
import json

def run_example():
    """Run the workflow with example data"""
    print("🚀 Running Open BIM Survey Workflow Example")
    print("=" * 50)
    
    # Paths
    example_csv = Path("data/raw/example_survey.csv")
    config_file = Path("config/coordinate_systems.json")
    
    # Check if files exist
    if not example_csv.exists():
        print(f"❌ Example CSV not found: {example_csv}")
        return False
    
    if not config_file.exists():
        print(f"❌ Config file not found: {config_file}")
        return False
    
    # Load config
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    print(f"📁 Input file: {example_csv}")
    print(f"⚙️  Source CRS: EPSG:{config['source_crs']['epsg']}")
    print(f"⚙️  Target CRS: EPSG:{config['target_crs']['epsg']}")
    print()
    
    # Step 1: Validate input
    print("Step 1: Validating input CSV...")
    if not validate_csv_format(example_csv):
        return False
    print()
    
    # Step 2: Process with pandas (fallback)
    print("Step 2: Processing coordinates...")
    processed_csv = Path("data/processed/example_survey.csv")
    processed_csv.parent.mkdir(exist_ok=True)
    
    success = process_survey_csv_pandas(example_csv, processed_csv, config)
    if not success:
        return False
    print()
    
    # Step 3: Show results
    print("Step 3: Results summary")
    print(f"✅ Processed CSV: {processed_csv}")
    
    # Read and display processed data
    import pandas as pd
    df = pd.read_csv(processed_csv)
    print(f"📊 Points processed: {len(df)}")
    print(f"📊 Coordinate ranges after transformation:")
    print(f"   X: {df['X'].min():.3f} to {df['X'].max():.3f}")
    print(f"   Y: {df['Y'].min():.3f} to {df['Y'].max():.3f}")
    if 'Z' in df.columns:
        print(f"   Z: {df['Z'].min():.3f} to {df['Z'].max():.3f}")
    print()
    
    print("🎯 Next steps:")
    print("1. Install Blender with Bonsai addon")
    print("2. Run: python scripts/blender/survey_importer.py data/processed/example_survey.csv data/output/example.ifc")
    print("3. Open the .blend file in Blender to review the 3D model")
    print("4. Export LandXML for machine control")
    print()
    
    print("✅ Example workflow completed successfully!")
    return True

if __name__ == "__main__":
    success = run_example()
    sys.exit(0 if success else 1)