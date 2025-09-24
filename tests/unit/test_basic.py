#!/usr/bin/env python3
"""
Basic test script that validates the project structure and example data
without requiring external dependencies
"""

import csv
import json
from pathlib import Path

def test_project_structure():
    """Test that all required directories and files exist"""
    print("🔍 Testing project structure...")
    
    required_dirs = [
        "data/raw",
        "data/processed", 
        "data/output",
        "experiments/blender",
        "src/core/converters",
        "experiments/qgis",
        "config",
        "templates"
    ]
    
    required_files = [
        "config/coordinate_systems.json",
        "data/raw/example_survey.csv",
        "experiments/prototypes/process_survey.py",
        "experiments/blender/survey_importer.py",
        "src/core/converters/ifc_to_landxml.py",
        "requirements.txt",
        "README.md"
    ]
    
    # Check directories
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            print(f"✅ Directory: {dir_path}")
        else:
            print(f"❌ Missing directory: {dir_path}")
            return False
    
    # Check files
    for file_path in required_files:
        path = Path(file_path)
        if path.exists() and path.is_file():
            print(f"✅ File: {file_path}")
        else:
            print(f"❌ Missing file: {file_path}")
            return False
    
    return True

def test_config_file():
    """Test configuration file format"""
    print("\n🔍 Testing configuration...")
    
    config_path = Path("config/coordinate_systems.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        required_keys = ['source_crs', 'target_crs', 'local_origin', 'precision']
        for key in required_keys:
            if key in config:
                print(f"✅ Config key: {key}")
            else:
                print(f"❌ Missing config key: {key}")
                return False
        
        # Test CRS structure
        if 'epsg' in config['source_crs'] and 'epsg' in config['target_crs']:
            print(f"✅ EPSG codes: {config['source_crs']['epsg']} -> {config['target_crs']['epsg']}")
        else:
            print("❌ Missing EPSG codes in CRS configuration")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Config file error: {e}")
        return False

def test_example_data():
    """Test example survey data format"""
    print("\n🔍 Testing example data...")
    
    csv_path = Path("data/raw/example_survey.csv")
    try:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            
            required_fields = ['ID', 'X', 'Y']
            for field in required_fields:
                if field in fieldnames:
                    print(f"✅ Required field: {field}")
                else:
                    print(f"❌ Missing required field: {field}")
                    return False
            
            # Read and validate data
            points = list(reader)
            print(f"✅ Data points: {len(points)}")
            
            # Check first point
            if points:
                first_point = points[0]
                try:
                    x = float(first_point['X'])
                    y = float(first_point['Y'])
                    print(f"✅ Coordinate validation: X={x}, Y={y}")
                except ValueError:
                    print("❌ Invalid coordinate format")
                    return False
            
            # Show data summary
            print(f"✅ Fields: {fieldnames}")
            print(f"✅ Sample point: {points[0] if points else 'No data'}")
            
        return True
        
    except Exception as e:
        print(f"❌ Example data error: {e}")
        return False

def test_coordinate_transformation_logic():
    """Test coordinate transformation logic without external dependencies"""
    print("\n🔍 Testing coordinate transformation logic...")
    
    # Simple test of coordinate offset calculation
    # This simulates what would happen with real coordinate transformation
    
    # Example large coordinates (typical GPS in UTM)
    large_coords = [
        (6400123.456, 5200789.123, 145.678),
        (6400145.789, 5200801.456, 146.234),
        (6400167.234, 5200823.789, 147.123)
    ]
    
    # Calculate local origin (center of points)
    x_coords = [p[0] for p in large_coords]
    y_coords = [p[1] for p in large_coords]
    z_coords = [p[2] for p in large_coords]
    
    origin_x = sum(x_coords) / len(x_coords)
    origin_y = sum(y_coords) / len(y_coords)
    origin_z = sum(z_coords) / len(z_coords)
    
    print(f"✅ Calculated origin: ({origin_x:.3f}, {origin_y:.3f}, {origin_z:.3f})")
    
    # Transform to local coordinates
    local_coords = []
    for x, y, z in large_coords:
        local_x = x - origin_x
        local_y = y - origin_y
        local_z = z - origin_z
        local_coords.append((local_x, local_y, local_z))
    
    print("✅ Local coordinates:")
    for i, (x, y, z) in enumerate(local_coords):
        print(f"   Point {i+1}: ({x:.3f}, {y:.3f}, {z:.3f})")
    
    # Verify coordinates are now small
    max_coord = max(abs(coord) for point in local_coords for coord in point)
    if max_coord < 100:
        print(f"✅ Coordinates successfully reduced (max: {max_coord:.3f})")
        return True
    else:
        print(f"❌ Coordinates still too large (max: {max_coord:.3f})")
        return False

def create_simple_landxml_example():
    """Create a simple LandXML example without dependencies"""
    print("\n🔍 Creating simple LandXML example...")
    
    # Simple XML structure
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<LandXML xmlns="http://www.landxml.org/schema/LandXML-1.2" version="1.2">
  <CoordinateSystem epsgCode="3857" name="Web Mercator"/>
  <Project name="Example Survey Project">
    <Application name="Open BIM Survey Workflow" version="1.0"/>
  </Project>
  <Surfaces>
    <Surface name="Example_Terrain">
      <Definition surfType="TIN">
        <Pnts>
          <P id="1">123.456 789.123 145.678</P>
          <P id="2">145.789 801.456 146.234</P>
          <P id="3">167.234 823.789 147.123</P>
        </Pnts>
        <Faces>
          <F>1 2 3</F>
        </Faces>
      </Definition>
    </Surface>
  </Surfaces>
</LandXML>'''
    
    output_path = Path("data/output/example.xml")
    output_path.parent.mkdir(exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    
    print(f"✅ Created example LandXML: {output_path}")
    return True

def main():
    """Run all tests"""
    print("🚀 Open BIM Survey Workflow - Basic Tests")
    print("=" * 50)
    
    tests = [
        ("Project Structure", test_project_structure),
        ("Configuration", test_config_file),
        ("Example Data", test_example_data),
        ("Coordinate Logic", test_coordinate_transformation_logic),
        ("LandXML Example", create_simple_landxml_example)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with error: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! Project structure is ready.")
        print("\n📋 Next steps:")
        print("1. Install Python dependencies: pip install -r requirements.txt")
        print("2. Install Blender with Bonsai addon")
        print("3. Configure coordinate systems in config/coordinate_systems.json")
        print("4. Run: python experiments/prototypes/process_survey.py data/raw/example_survey.csv")
    else:
        print(f"\n⚠️  {len(results) - passed} tests failed. Please fix issues before proceeding.")
    
    return passed == len(results)

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)