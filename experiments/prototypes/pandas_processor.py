"""
Fallback CSV processor using pandas and pyproj
Used when QGIS is not available
"""

import pandas as pd
import numpy as np
from pyproj import Transformer
import json
from pathlib import Path

def process_survey_csv_pandas(input_file, output_file, config):
    """Process survey CSV with pandas and pyproj coordinate transformation"""
    print(f"Processing {input_file} with pandas/pyproj fallback")
    
    try:
        # Read CSV
        df = pd.read_csv(input_file)
        
        # Validate required columns
        required_cols = ['X', 'Y']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Set up coordinate transformation
        source_epsg = config['source_crs']['epsg']
        target_epsg = config['target_crs']['epsg']
        
        transformer = Transformer.from_crs(
            f"EPSG:{source_epsg}", 
            f"EPSG:{target_epsg}", 
            always_xy=True
        )
        
        # Transform coordinates
        print(f"Transforming coordinates: EPSG:{source_epsg} -> EPSG:{target_epsg}")
        
        # Handle potential NaN values
        valid_coords = df[['X', 'Y']].notna().all(axis=1)
        
        if valid_coords.sum() == 0:
            raise ValueError("No valid coordinate pairs found")
        
        # Transform valid coordinates
        x_transformed, y_transformed = transformer.transform(
            df.loc[valid_coords, 'X'].values,
            df.loc[valid_coords, 'Y'].values
        )
        
        # Apply local origin offset
        local_origin = config.get('local_origin', {'x': 0, 'y': 0, 'z': 0})
        x_transformed = x_transformed - local_origin['x']
        y_transformed = y_transformed - local_origin['y']
        
        # Update dataframe
        df.loc[valid_coords, 'X'] = x_transformed
        df.loc[valid_coords, 'Y'] = y_transformed
        
        # Handle Z coordinate if present
        if 'Z' in df.columns:
            df.loc[valid_coords, 'Z'] = df.loc[valid_coords, 'Z'] - local_origin['z']
        
        # Round to specified precision
        precision = config.get('precision', {}).get('decimal_places', 3)
        df['X'] = df['X'].round(precision)
        df['Y'] = df['Y'].round(precision)
        if 'Z' in df.columns:
            df['Z'] = df['Z'].round(precision)
        
        # Remove rows with invalid coordinates
        df_clean = df[valid_coords].copy()
        
        # Clean up data types and remove unnecessary columns
        # Keep only essential columns: ID, Description, Code, X, Y, Z
        essential_cols = ['ID', 'Description', 'Code', 'X', 'Y']
        if 'Z' in df_clean.columns:
            essential_cols.append('Z')
        
        # Keep only columns that exist
        keep_cols = [col for col in essential_cols if col in df_clean.columns]
        df_final = df_clean[keep_cols].copy()
        
        # Fill missing values
        if 'Description' in df_final.columns:
            df_final['Description'] = df_final['Description'].fillna('')
        if 'Code' in df_final.columns:
            df_final['Code'] = df_final['Code'].fillna('UNKNOWN')
        if 'ID' in df_final.columns:
            df_final['ID'] = df_final['ID'].fillna(range(1, len(df_final) + 1))
        
        # Save processed CSV
        df_final.to_csv(output_file, index=False)
        
        print(f"✅ Processed {len(df_final)} points -> {output_file}")
        print(f"Columns: {list(df_final.columns)}")
        
        # Print summary statistics
        if len(df_final) > 0:
            print(f"Coordinate ranges:")
            print(f"  X: {df_final['X'].min():.3f} to {df_final['X'].max():.3f}")
            print(f"  Y: {df_final['Y'].min():.3f} to {df_final['Y'].max():.3f}")
            if 'Z' in df_final.columns:
                print(f"  Z: {df_final['Z'].min():.3f} to {df_final['Z'].max():.3f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing CSV: {e}")
        return False

def validate_csv_format(csv_file):
    """Validate that CSV has required format for survey data"""
    try:
        df = pd.read_csv(csv_file, nrows=5)  # Just check first few rows
        
        required_cols = ['X', 'Y']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            print(f"❌ Missing required columns: {missing_cols}")
            print(f"Available columns: {list(df.columns)}")
            return False
        
        # Check if coordinates are numeric
        for col in ['X', 'Y']:
            if not pd.api.types.is_numeric_dtype(df[col]):
                print(f"❌ Column {col} is not numeric")
                return False
        
        print(f"✅ CSV format is valid")
        print(f"Columns: {list(df.columns)}")
        print(f"Sample data:")
        print(df.head())
        
        return True
        
    except Exception as e:
        print(f"❌ Error validating CSV: {e}")
        return False

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) >= 3:
        input_file = sys.argv[1]
        output_file = sys.argv[2]
        
        # Load config
        config_path = Path("config/coordinate_systems.json")
        if config_path.exists():
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            # Default config
            config = {
                "source_crs": {"epsg": 4326},
                "target_crs": {"epsg": 3857},
                "local_origin": {"x": 0, "y": 0, "z": 0},
                "precision": {"decimal_places": 3}
            }
        
        # Validate input first
        if validate_csv_format(input_file):
            process_survey_csv_pandas(input_file, output_file, config)
    else:
        print("Usage: python pandas_processor.py input.csv output.csv")