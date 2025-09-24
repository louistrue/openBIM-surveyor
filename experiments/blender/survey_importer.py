"""
Blender script for importing survey points and creating IFC 4x3 model
Requires Bonsai addon to be installed and enabled
"""

import bpy
import bmesh
import csv
import json
from pathlib import Path
from mathutils import Vector

def clear_scene():
    """Clear existing mesh objects"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def setup_collections():
    """Create organized collections for survey data"""
    collections = {}
    
    # Main survey collection
    survey_collection = bpy.data.collections.new("Survey Points")
    bpy.context.scene.collection.children.link(survey_collection)
    
    # Sub-collections by code (will be created as needed)
    collections['survey'] = survey_collection
    collections['by_code'] = {}
    
    return collections

def create_survey_point(point_data, collections):
    """Create a survey point as IfcAnnotation with metadata"""
    x, y, z = float(point_data['X']), float(point_data['Y']), float(point_data['Z'])
    point_id = point_data['ID']
    description = point_data.get('Description', '')
    code = point_data.get('Code', 'UNKNOWN')
    
    # Create a small sphere to represent the point
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, location=(x, y, z))
    point_obj = bpy.context.active_object
    point_obj.name = f"Survey_Point_{point_id}"
    
    # Create collection for this code if it doesn't exist
    if code not in collections['by_code']:
        code_collection = bpy.data.collections.new(f"Code_{code}")
        collections['survey'].children.link(code_collection)
        collections['by_code'][code] = code_collection
    
    # Move object to appropriate collection
    bpy.context.scene.collection.objects.unlink(point_obj)
    collections['by_code'][code].objects.link(point_obj)
    
    # Add custom properties for IFC export
    point_obj['IFC_Type'] = 'IfcAnnotation'
    point_obj['IFC_PredefinedType'] = 'SURVEY'
    point_obj['Survey_ID'] = point_id
    point_obj['Survey_Description'] = description
    point_obj['Survey_Code'] = code
    point_obj['Survey_X'] = x
    point_obj['Survey_Y'] = y
    point_obj['Survey_Z'] = z
    
    return point_obj

def create_terrain_surface(points, collections):
    """Create a basic terrain surface from survey points"""
    if len(points) < 3:
        print("Not enough points for terrain surface")
        return None
    
    # Create new mesh
    mesh = bpy.data.meshes.new("Terrain_Surface")
    terrain_obj = bpy.data.objects.new("Terrain_Surface", mesh)
    
    # Create terrain collection if needed
    if 'terrain' not in collections:
        terrain_collection = bpy.data.collections.new("Terrain")
        bpy.context.scene.collection.children.link(terrain_collection)
        collections['terrain'] = terrain_collection
    
    collections['terrain'].objects.link(terrain_obj)
    
    # Create bmesh for terrain
    bm = bmesh.new()
    
    # Add vertices from survey points
    vertices = []
    for point in points:
        x, y, z = float(point['X']), float(point['Y']), float(point['Z'])
        vert = bm.verts.new((x, y, z))
        vertices.append(vert)
    
    # Simple Delaunay triangulation (basic implementation)
    # For production, consider using scipy.spatial.Delaunay
    bm.verts.ensure_lookup_table()
    
    # Create faces using convex hull as approximation
    try:
        bmesh.ops.convex_hull(bm, input=vertices)
    except:
        print("Could not create terrain surface - using simple triangulation")
        # Fallback: create simple triangular faces
        if len(vertices) >= 3:
            for i in range(len(vertices) - 2):
                bm.faces.new([vertices[0], vertices[i+1], vertices[i+2]])
    
    # Update mesh
    bm.to_mesh(mesh)
    bm.free()
    
    # Set IFC properties for terrain
    terrain_obj['IFC_Type'] = 'IfcGeographicElement'
    terrain_obj['IFC_PredefinedType'] = 'TERRAIN'
    
    return terrain_obj

def setup_ifc_project(config):
    """Setup IFC project context with georeferencing"""
    try:
        import bonsai.tool.project as project_tool
        
        # Create new IFC project
        bpy.ops.bim.create_project()
        
        # Set up coordinate reference system
        source_crs = config.get('source_crs', {})
        target_crs = config.get('target_crs', {})
        
        # This would need to be adapted based on Bonsai's current API
        # The exact implementation depends on Bonsai version
        print(f"Setting up IFC project with CRS: {target_crs.get('name', 'Unknown')}")
        
    except ImportError:
        print("Bonsai not available - creating basic Blender scene")
    except Exception as e:
        print(f"Error setting up IFC project: {e}")

def import_survey_points(csv_file, ifc_output, config):
    """Main function to import survey points and export IFC"""
    print(f"Importing survey points from {csv_file}")
    
    # Clear scene and setup
    clear_scene()
    collections = setup_collections()
    setup_ifc_project(config)
    
    # Read CSV data
    points = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append(row)
            create_survey_point(row, collections)
    
    print(f"Created {len(points)} survey point objects")
    
    # Create terrain surface if we have enough points
    if len(points) >= 3:
        create_terrain_surface(points, collections)
        print("Created terrain surface")
    
    # Save Blender file
    blend_output = str(ifc_output).replace('.ifc', '.blend')
    bpy.ops.wm.save_as_mainfile(filepath=blend_output)
    print(f"Saved Blender file: {blend_output}")
    
    # Export IFC (requires Bonsai)
    try:
        bpy.ops.export_ifc.bim(filepath=str(ifc_output))
        print(f"Exported IFC file: {ifc_output}")
    except:
        print("IFC export failed - Bonsai addon may not be installed")
        print("Manual export required through Bonsai addon")

if __name__ == "__main__":
    # Example usage when run directly in Blender
    import sys
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
        ifc_output = sys.argv[2] if len(sys.argv) > 2 else "output.ifc"
        config = {"source_crs": {"epsg": 4326}, "target_crs": {"epsg": 3857}}
        import_survey_points(csv_file, ifc_output, config)