#!/usr/bin/env python3
"""
Specialized processor for client survey data format
Handles semicolon-separated values and specific column mapping
"""

import pandas as pd
import numpy as np
from pyproj import Transformer
import json
from pathlib import Path

def process_client_csv(input_file, output_file, config):
    """Process client CSV with semicolon separators and specific format"""
    print(f"Processing client data: {input_file}")
    
    try:
        # Read CSV with semicolon separator
        df = pd.read_csv(input_file, sep=';')
        
        # Show original columns
        print(f"Original columns: {list(df.columns)}")
        
        # Map client columns to standard format
        column_mapping = {
            'localId': 'ID',
            'y': 'Y',  # Note: client has Y,X instead of X,Y
            'x': 'X',
            'z': 'Z',
            'code': 'Code',
            'description': 'Description'
        }
        
        # Check if required columns exist
        required_cols = ['localId', 'y', 'x', 'z']
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")
        
        # Select and rename columns
        df_clean = df[list(column_mapping.keys())].copy()
        df_clean = df_clean.rename(columns=column_mapping)
        
        # Remove rows with NaN coordinates
        df_clean = df_clean.dropna(subset=['X', 'Y', 'Z'])
        
        print(f"Valid points after cleaning: {len(df_clean)}")
        
        # Set up coordinate transformation
        source_epsg = config['source_crs']['epsg']
        target_epsg = config['target_crs']['epsg']
        
        # For this client data, we'll assume it's already in a projected system
        # and just apply local origin transformation
        print(f"Applying local origin transformation...")
        
        # Calculate local origin from data bounds
        x_coords = df_clean['X'].values
        y_coords = df_clean['Y'].values
        z_coords = df_clean['Z'].values
        
        # Use center of bounding box as local origin
        origin_x = (x_coords.min() + x_coords.max()) / 2
        origin_y = (y_coords.min() + y_coords.max()) / 2
        origin_z = z_coords.min()  # Use minimum Z as base level
        
        print(f"Calculated local origin: ({origin_x:.3f}, {origin_y:.3f}, {origin_z:.3f})")
        
        # Apply local origin offset
        df_clean['X'] = df_clean['X'] - origin_x
        df_clean['Y'] = df_clean['Y'] - origin_y
        df_clean['Z'] = df_clean['Z'] - origin_z
        
        # Round to specified precision
        precision = config.get('precision', {}).get('decimal_places', 3)
        df_clean['X'] = df_clean['X'].round(precision)
        df_clean['Y'] = df_clean['Y'].round(precision)
        df_clean['Z'] = df_clean['Z'].round(precision)
        
        # Clean up text fields
        df_clean['Description'] = df_clean['Description'].fillna('')
        df_clean['Code'] = df_clean['Code'].fillna('UNKNOWN')
        
        # Add local origin point as reference
        origin_row = {
            'ID': 'ORIGIN',
            'X': 0.0,
            'Y': 0.0,
            'Z': 0.0,
            'Code': 'ORIGIN',
            'Description': f'Local origin ({origin_x:.3f}, {origin_y:.3f}, {origin_z:.3f})'
        }
        df_clean = pd.concat([pd.DataFrame([origin_row]), df_clean], ignore_index=True)
        
        # Save processed CSV
        df_clean.to_csv(output_file, index=False)
        
        print(f"✅ Processed {len(df_clean)} points -> {output_file}")
        print(f"Coordinate ranges after transformation:")
        print(f"  X: {df_clean['X'].min():.3f} to {df_clean['X'].max():.3f}")
        print(f"  Y: {df_clean['Y'].min():.3f} to {df_clean['Y'].max():.3f}")
        print(f"  Z: {df_clean['Z'].min():.3f} to {df_clean['Z'].max():.3f}")
        
        # Show point codes summary
        code_counts = df_clean['Code'].value_counts()
        print(f"Point codes: {dict(code_counts)}")
        
        # Store transformation info for later use
        transform_info = {
            'local_origin': {
                'x': float(origin_x),
                'y': float(origin_y),
                'z': float(origin_z)
            },
            'point_count': len(df_clean),
            'coordinate_ranges': {
                'x_min': float(df_clean['X'].min()),
                'x_max': float(df_clean['X'].max()),
                'y_min': float(df_clean['Y'].min()),
                'y_max': float(df_clean['Y'].max()),
                'z_min': float(df_clean['Z'].min()),
                'z_max': float(df_clean['Z'].max())
            }
        }
        
        transform_file = str(output_file).replace('.csv', '_transform_info.json')
        with open(transform_file, 'w') as f:
            json.dump(transform_info, f, indent=2)
        
        print(f"✅ Transformation info saved: {transform_file}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing client CSV: {e}")
        return False

def compare_with_reference(processed_file, reference_file):
    """Compare our processed output with the reference QGIS output"""
    print(f"\n🔍 Comparing with reference output...")
    
    try:
        # Read both files
        our_df = pd.read_csv(processed_file)
        ref_df = pd.read_csv(reference_file)
        
        print(f"Our output: {len(our_df)} points")
        print(f"Reference: {len(ref_df)} points")
        
        # Compare coordinate ranges
        print(f"\nCoordinate comparison:")
        print(f"Our X range: {our_df['X'].min():.3f} to {our_df['X'].max():.3f}")
        print(f"Ref X range: {ref_df['x'].min():.3f} to {ref_df['x'].max():.3f}")
        print(f"Our Y range: {our_df['Y'].min():.3f} to {our_df['Y'].max():.3f}")
        print(f"Ref Y range: {ref_df['y'].min():.3f} to {ref_df['y'].max():.3f}")
        
        # Check if we have similar coordinate transformation
        # (allowing for different local origins)
        our_span_x = our_df['X'].max() - our_df['X'].min()
        our_span_y = our_df['Y'].max() - our_df['Y'].min()
        ref_span_x = ref_df['x'].max() - ref_df['x'].min()
        ref_span_y = ref_df['y'].max() - ref_df['y'].min()
        
        print(f"\nCoordinate spans:")
        print(f"Our spans: X={our_span_x:.3f}, Y={our_span_y:.3f}")
        print(f"Ref spans: X={ref_span_x:.3f}, Y={ref_span_y:.3f}")
        
        span_diff_x = abs(our_span_x - ref_span_x)
        span_diff_y = abs(our_span_y - ref_span_y)
        
        if span_diff_x < 1.0 and span_diff_y < 1.0:
            print("✅ Coordinate spans match well - transformation is consistent")
        else:
            print("⚠️  Coordinate spans differ - may need adjustment")
        
        return True
        
    except Exception as e:
        print(f"❌ Error comparing files: {e}")
        return False

def main():
    """Test with client data"""
    print("🚀 Client Data Processing Test")
    print("=" * 50)
    
    # File paths
    input_file = Path("data/raw/client_survey.csv")
    output_file = Path("data/processed/client_survey_processed.csv")
    reference_file = Path("data/processed/reference_output.csv")
    config_file = Path("config/coordinate_systems.json")
    
    # Check files exist
    if not input_file.exists():
        print(f"❌ Input file not found: {input_file}")
        return False
    
    # Load config
    if config_file.exists():
        with open(config_file, 'r') as f:
            config = json.load(f)
    else:
        # Default config for client data
        config = {
            "source_crs": {"epsg": 3006, "name": "SWEREF99 TM"},  # Common Swedish system
            "target_crs": {"epsg": 3006, "name": "SWEREF99 TM"},  # Keep same for now
            "local_origin": {"x": 0, "y": 0, "z": 0},
            "precision": {"decimal_places": 3}
        }
    
    # Process client data
    success = process_client_csv(input_file, output_file, config)
    
    if success and reference_file.exists():
        compare_with_reference(output_file, reference_file)
    
    return success

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)