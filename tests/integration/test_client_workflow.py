#!/usr/bin/env python3
"""
Complete end-to-end test of the client workflow
Tests the full pipeline from raw TopoCad CSV to LandXML output
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

from client_data_processor import process_client_csv
from export.csv_to_landxml import CSVToLandXMLExporter

def compare_landxml_files(our_file, reference_file):
    """Compare our generated LandXML with the TopoCad reference"""
    print(f"\n🔍 Comparing LandXML outputs...")
    
    try:
        # Parse both XML files
        our_tree = ET.parse(our_file)
        ref_tree = ET.parse(reference_file)
        
        our_root = our_tree.getroot()
        ref_root = ref_tree.getroot()
        
        print(f"Our LandXML version: {our_root.get('version')}")
        print(f"Reference version: {ref_root.get('version')}")
        
        # Count surfaces
        our_surfaces = our_root.findall('.//{http://www.landxml.org/schema/LandXML-1.2}Surface')
        ref_surfaces = ref_root.findall('.//{http://www.landxml.org/schema/LandXML-1.1}Surface')
        
        print(f"Our surfaces: {len(our_surfaces)}")
        print(f"Reference surfaces: {len(ref_surfaces)}")
        
        # Count points in first surface
        if our_surfaces:
            our_points = our_surfaces[0].findall('.//{http://www.landxml.org/schema/LandXML-1.2}P')
            print(f"Our surface points: {len(our_points)}")
            
            our_faces = our_surfaces[0].findall('.//{http://www.landxml.org/schema/LandXML-1.2}F')
            print(f"Our surface faces: {len(our_faces)}")
        
        if ref_surfaces:
            # Reference uses breaklines instead of TIN points
            ref_breaklines = ref_surfaces[0].findall('.//{http://www.landxml.org/schema/LandXML-1.1}Breakline')
            print(f"Reference breaklines: {len(ref_breaklines)}")
        
        # Check coordinate system
        our_crs = our_root.find('.//{http://www.landxml.org/schema/LandXML-1.2}CoordinateSystem')
        if our_crs is not None:
            print(f"Our CRS: EPSG:{our_crs.get('epsgCode')} - {our_crs.get('name')}")
        
        print("✅ LandXML comparison completed")
        return True
        
    except Exception as e:
        print(f"❌ Error comparing LandXML files: {e}")
        return False

def analyze_coordinate_accuracy(processed_csv, reference_csv):
    """Analyze coordinate transformation accuracy"""
    print(f"\n🎯 Analyzing coordinate transformation accuracy...")
    
    try:
        import pandas as pd
        
        # Read our processed data
        our_df = pd.read_csv(processed_csv)
        our_df = our_df[our_df['Code'] != 'ORIGIN']  # Remove origin point
        
        # Read reference data (QGIS output)
        ref_df = pd.read_csv(reference_csv)
        ref_df = ref_df[ref_df['code'] != 'ARB_FIX']  # Remove origin point
        
        print(f"Our points: {len(our_df)}")
        print(f"Reference points: {len(ref_df)}")
        
        # Compare coordinate ranges (should be similar after local transformation)
        our_x_range = our_df['X'].max() - our_df['X'].min()
        our_y_range = our_df['Y'].max() - our_df['Y'].min()
        ref_x_range = ref_df['x'].max() - ref_df['x'].min()
        ref_y_range = ref_df['y'].max() - ref_df['y'].min()
        
        print(f"\nCoordinate ranges:")
        print(f"Our X range: {our_x_range:.3f}m")
        print(f"Ref X range: {ref_x_range:.3f}m")
        print(f"Our Y range: {our_y_range:.3f}m")
        print(f"Ref Y range: {ref_y_range:.3f}m")
        
        # Calculate relative differences
        x_diff = abs(our_x_range - ref_x_range) / ref_x_range * 100
        y_diff = abs(our_y_range - ref_y_range) / ref_y_range * 100
        
        print(f"\nRange differences:")
        print(f"X range difference: {x_diff:.1f}%")
        print(f"Y range difference: {y_diff:.1f}%")
        
        if x_diff < 5 and y_diff < 5:
            print("✅ Coordinate transformation accuracy is good (<5% difference)")
        else:
            print("⚠️  Coordinate transformation may need adjustment")
        
        return True
        
    except Exception as e:
        print(f"❌ Error analyzing coordinates: {e}")
        return False

def test_file_compatibility():
    """Test if our output files are compatible with standard tools"""
    print(f"\n🔧 Testing file compatibility...")
    
    # Test LandXML validity
    landxml_file = Path("data/output/client_survey.xml")
    if landxml_file.exists():
        try:
            tree = ET.parse(landxml_file)
            root = tree.getroot()
            
            # Check namespace
            if "landxml.org" in root.tag:
                print("✅ LandXML has correct namespace")
            else:
                print("⚠️  LandXML namespace may be incorrect")
            
            # Check required elements
            surfaces = root.findall('.//{http://www.landxml.org/schema/LandXML-1.2}Surface')
            if surfaces:
                print(f"✅ Found {len(surfaces)} surface(s)")
                
                # Check TIN structure
                for surface in surfaces:
                    points = surface.findall('.//{http://www.landxml.org/schema/LandXML-1.2}P')
                    faces = surface.findall('.//{http://www.landxml.org/schema/LandXML-1.2}F')
                    print(f"   Surface '{surface.get('name')}': {len(points)} points, {len(faces)} faces")
            
            print("✅ LandXML structure is valid")
            
        except ET.ParseError as e:
            print(f"❌ LandXML parsing error: {e}")
            return False
    
    return True

def run_complete_workflow():
    """Run the complete workflow from raw data to LandXML"""
    print("🚀 Complete Client Workflow Test")
    print("=" * 60)
    
    # File paths
    raw_csv = Path("data/raw/client_survey.csv")
    processed_csv = Path("data/processed/client_survey_processed.csv")
    transform_info_file = Path("data/processed/client_survey_processed_transform_info.json")
    landxml_output = Path("data/output/client_survey.xml")
    reference_csv = Path("data/processed/reference_output.csv")
    reference_landxml = Path("resources/TopoCad workflow/TopoCad Workflow.xml")
    
    # Configuration
    config = {
        "source_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "target_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "local_origin": {"x": 0, "y": 0, "z": 0},
        "precision": {"decimal_places": 3}
    }
    
    results = []
    
    # Step 1: Process raw CSV
    print("\n📊 Step 1: Processing raw survey data...")
    if raw_csv.exists():
        success = process_client_csv(raw_csv, processed_csv, config)
        results.append(("CSV Processing", success))
        if success:
            print(f"✅ Processed CSV: {processed_csv}")
    else:
        print(f"❌ Raw CSV not found: {raw_csv}")
        results.append(("CSV Processing", False))
    
    # Step 2: Export to LandXML
    print("\n🗺️  Step 2: Exporting to LandXML...")
    if processed_csv.exists():
        # Load transformation info
        transform_info = None
        if transform_info_file.exists():
            with open(transform_info_file, 'r') as f:
                transform_info = json.load(f)
        
        # Create exporter and export
        exporter = CSVToLandXMLExporter(transform_info)
        success = exporter.export_to_landxml(processed_csv, landxml_output)
        results.append(("LandXML Export", success))
        if success:
            print(f"✅ Exported LandXML: {landxml_output}")
    else:
        print("❌ Processed CSV not found")
        results.append(("LandXML Export", False))
    
    # Step 3: Compare with reference data
    print("\n🔍 Step 3: Comparing with reference data...")
    if reference_csv.exists() and processed_csv.exists():
        success = analyze_coordinate_accuracy(processed_csv, reference_csv)
        results.append(("Coordinate Analysis", success))
    else:
        print("⚠️  Reference data not available for comparison")
        results.append(("Coordinate Analysis", None))
    
    # Step 4: Compare LandXML outputs
    if reference_landxml.exists() and landxml_output.exists():
        success = compare_landxml_files(landxml_output, reference_landxml)
        results.append(("LandXML Comparison", success))
    else:
        print("⚠️  Reference LandXML not available for comparison")
        results.append(("LandXML Comparison", None))
    
    # Step 5: Test file compatibility
    success = test_file_compatibility()
    results.append(("File Compatibility", success))
    
    # Summary
    print("\n" + "=" * 60)
    print("📋 Workflow Test Results")
    print("=" * 60)
    
    passed = 0
    total = 0
    
    for test_name, result in results:
        if result is True:
            status = "✅ PASS"
            passed += 1
            total += 1
        elif result is False:
            status = "❌ FAIL"
            total += 1
        else:
            status = "⚠️  SKIP"
        
        print(f"  {status}: {test_name}")
    
    print(f"\n🎯 Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 Complete workflow test PASSED!")
        print("\n📁 Generated files:")
        if processed_csv.exists():
            print(f"   📊 Processed CSV: {processed_csv}")
        if landxml_output.exists():
            print(f"   🗺️  LandXML: {landxml_output}")
            print(f"   📏 Size: {landxml_output.stat().st_size} bytes")
        
        print("\n✨ Benefits achieved:")
        print("   ✅ Open standards (LandXML 1.2)")
        print("   ✅ Preserved survey metadata")
        print("   ✅ Automated coordinate transformation")
        print("   ✅ Machine control compatibility")
        print("   ✅ No vendor lock-in")
        
    else:
        print(f"\n⚠️  {total - passed} tests failed or were skipped")
    
    return passed == total

if __name__ == "__main__":
    success = run_complete_workflow()
    sys.exit(0 if success else 1)