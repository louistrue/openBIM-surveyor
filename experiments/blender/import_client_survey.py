
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
                    
                    # Move to survey collection safely
                    if point_obj.users_collection:
                        for collection in point_obj.users_collection:
                            collection.objects.unlink(point_obj)
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
    csv_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\processed\client_survey_processed.csv"
    
    # Import survey points
    import_survey_points_simple(csv_file)
    
    # Save blend file
    blend_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\output\client_survey.blend"
    bpy.ops.wm.save_as_mainfile(filepath=blend_file)
    print(f"Saved Blender file: {blend_file}")
