#!/usr/bin/env python3
"""
Test script for Blender import functionality
This can be run inside Blender or as a standalone test
"""

import csv
import json
import sys
from pathlib import Path

def create_blender_test_script():
    """Create a Blender script that can be run manually"""
    
    blender_script = '''
# Blender Survey Import Test Script
# Run this in Blender's Text Editor or via command line

import bpy
import bmesh
import csv
from mathutils import Vector

def clear_scene():
    """Clear existing mesh objects"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def import_survey_points_simple(csv_file):
    """Simple import of survey points as mesh objects"""
    print(f"Importing survey points from: {csv_file}")
    
    # Clear scene
    clear_scene()
    
    # Create collection for survey points
    survey_collection = bpy.data.collections.new("Survey_Points")
    bpy.context.scene.collection.children.link(survey_collection)
    
    points = []
    
    # Read CSV data
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['Code'] != 'ORIGIN':  # Skip origin point
                try:
                    x = float(row['X'])
                    y = float(row['Y'])
                    z = float(row['Z'])
                    point_id = row['ID']
                    code = row['Code']
                    description = row['Description']
                    
                    # Create small sphere for each point
                    bpy.ops.mesh.primitive_uv_sphere_add(
                        radius=0.5, 
                        location=(x, y, z)
                    )
                    
                    point_obj = bpy.context.active_object
                    point_obj.name = f"Point_{point_id}"
                    
                    # Add custom properties
                    point_obj['Survey_ID'] = point_id
                    point_obj['Survey_Code'] = code
                    point_obj['Survey_Description'] = description
                    
                    # Move to survey collection
                    bpy.context.scene.collection.objects.unlink(point_obj)
                    survey_collection.objects.link(point_obj)
                    
                    points.append((x, y, z))
                    
                except (ValueError, KeyError) as e:
                    print(f"Skipping invalid point: {row} - {e}")
    
    print(f"Imported {len(points)} survey points")
    
    # Create simple terrain mesh
    if len(points) >= 3:
        create_terrain_mesh(points, survey_collection)
    
    # Set viewport shading to solid
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'
    
    print("Survey import completed!")

def create_terrain_mesh(points, collection):
    """Create a simple terrain mesh from points"""
    mesh = bpy.data.meshes.new("Terrain")
    terrain_obj = bpy.data.objects.new("Terrain", mesh)
    collection.objects.link(terrain_obj)
    
    # Create bmesh
    bm = bmesh.new()
    
    # Add vertices
    for x, y, z in points:
        bm.verts.new((x, y, z))
    
    # Create convex hull
    bm.verts.ensure_lookup_table()
    try:
        bmesh.ops.convex_hull(bm, input=bm.verts)
        print("Created terrain surface using convex hull")
    except:
        print("Convex hull failed, creating simple triangulation")
        # Simple triangulation fallback
        if len(bm.verts) >= 3:
            for i in range(len(bm.verts) - 2):
                try:
                    bm.faces.new([bm.verts[0], bm.verts[i+1], bm.verts[i+2]])
                except:
                    pass
    
    # Update mesh
    bm.to_mesh(mesh)
    bm.free()
    
    # Add material
    mat = bpy.data.materials.new(name="Terrain_Material")
    mat.diffuse_color = (0.6, 0.4, 0.2, 1.0)  # Brown color
    terrain_obj.data.materials.append(mat)

# Main execution
if __name__ == "__main__":
    # Path to processed CSV (adjust as needed)
    csv_file = r"C:\\Users\\louistrue\\Documents\\Dev\\bonsai-topo\\data\\processed\\client_survey_processed.csv"
    
    # Import survey points
    import_survey_points_simple(csv_file)
    
    # Save blend file
    blend_file = r"C:\\Users\\louistrue\\Documents\\Dev\\bonsai-topo\\data\\output\\client_survey.blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend_file)
    print(f"Saved Blender file: {blend_file}")
'''
    
    script_path = Path("scripts/blender/import_client_survey.py")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(blender_script)
    
    return script_path

def create_blender_batch_file():
    """Create a batch file to run Blender with our script"""
    
    batch_content = '''@echo off
echo Running Blender Survey Import...
echo ================================

REM Try common Blender installation paths
set BLENDER_PATH=""

if exist "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe" (
    set BLENDER_PATH="C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe"
) else if exist "C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe" (
    set BLENDER_PATH="C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe"
) else (
    echo Blender not found in common locations
    echo Please install Blender or update the path in this script
    pause
    exit /b 1
)

echo Found Blender at: %BLENDER_PATH%
echo.

REM Run Blender with our script
%BLENDER_PATH% --background --python scripts\\blender\\import_client_survey.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [SUCCESS] Blender import completed!
    echo [INFO] Check data\\output\\client_survey.blend
) else (
    echo.
    echo [ERROR] Blender import failed
)

pause
'''
    
    batch_path = Path("run_blender_import.bat")
    with open(batch_path, 'w', encoding='utf-8') as f:
        f.write(batch_content)
    
    return batch_path

def test_csv_data_for_blender():
    """Test that our CSV data is suitable for Blender import"""
    print("🔍 Testing CSV data for Blender compatibility...")
    
    csv_file = Path("data/processed/client_survey_processed.csv")
    
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return False
    
    try:
        points = []
        with open(csv_file, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Code'] != 'ORIGIN':
                    x = float(row['X'])
                    y = float(row['Y'])
                    z = float(row['Z'])
                    points.append((x, y, z))
        
        print(f"✅ Found {len(points)} valid points")
        
        # Check coordinate ranges (should be reasonable for Blender)
        if points:
            x_coords = [p[0] for p in points]
            y_coords = [p[1] for p in points]
            z_coords = [p[2] for p in points]
            
            x_range = max(x_coords) - min(x_coords)
            y_range = max(y_coords) - min(y_coords)
            z_range = max(z_coords) - min(z_coords)
            
            print(f"Coordinate ranges:")
            print(f"  X: {min(x_coords):.3f} to {max(x_coords):.3f} (range: {x_range:.3f})")
            print(f"  Y: {min(y_coords):.3f} to {max(y_coords):.3f} (range: {y_range:.3f})")
            print(f"  Z: {min(z_coords):.3f} to {max(z_coords):.3f} (range: {z_range:.3f})")
            
            # Check if coordinates are reasonable for Blender (not too large)
            max_coord = max(abs(coord) for point in points for coord in point)
            if max_coord < 1000:
                print("✅ Coordinates are suitable for Blender (< 1000 units)")
            else:
                print("⚠️  Coordinates are large - may cause precision issues in Blender")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing CSV data: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Blender Import Test Setup")
    print("=" * 40)
    
    # Test CSV data
    csv_ok = test_csv_data_for_blender()
    
    if not csv_ok:
        print("❌ CSV data test failed")
        return False
    
    # Create Blender script
    print("\n📝 Creating Blender import script...")
    script_path = create_blender_test_script()
    print(f"✅ Created: {script_path}")
    
    # Create batch file
    print("\n📝 Creating batch file...")
    batch_path = create_blender_batch_file()
    print(f"✅ Created: {batch_path}")
    
    print("\n" + "=" * 40)
    print("📋 Blender Import Instructions")
    print("=" * 40)
    
    print("\n🎯 Option 1: Automatic (if Blender is installed)")
    print(f"   Run: {batch_path}")
    
    print("\n🎯 Option 2: Manual in Blender")
    print("   1. Open Blender")
    print("   2. Go to Scripting workspace")
    print(f"   3. Open: {script_path}")
    print("   4. Click 'Run Script'")
    print("   5. Check the 3D viewport for imported points")
    
    print("\n🎯 Option 3: Command line")
    print(f'   blender --background --python "{script_path}"')
    
    print("\n✨ Expected Results:")
    print("   📊 26 survey points as small spheres")
    print("   🗻 Terrain surface mesh")
    print("   📁 Saved .blend file in data/output/")
    print("   🏷️  Custom properties on each point")
    
    print("\n📚 Next Steps (if Blender works):")
    print("   1. Install Bonsai addon in Blender")
    print("   2. Convert objects to IFC classes")
    print("   3. Export as IFC 4x3 file")
    print("   4. Use for BIM coordination")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)