"""
Simple Survey Point Visualizer for Blender
Copy and paste this script into Blender's Text Editor and run it
Works after importing IFC file with survey points via Bonsai addon
"""

import bpy
import bmesh

# Settings
COLLECTION_NAME = "Survey Points Vis"
SPHERE_RADIUS = 0.2
MAKE_LABELS = True
LABEL_SIZE = 0.3
LABEL_OFFSET = (0.4, 0.4, 0.2)

# Colors for different codes
COLORS = {
    'VAG_VM': (1.0, 0.3, 0.3, 1.0),  # Red
    'CORNER': (0.3, 1.0, 0.3, 1.0),  # Green  
    'TREE': (0.3, 0.8, 0.3, 1.0),    # Dark Green
    'ROAD': (0.5, 0.5, 0.5, 1.0),    # Gray
    'DEFAULT': (1.0, 1.0, 0.0, 1.0)  # Yellow
}

def create_material(name, color):
    """Create colored material"""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs[0].default_value = color
    return mat

def create_sphere(name, location, radius, material=None):
    """Create mesh sphere"""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=radius)
    bm.to_mesh(mesh)
    bm.free()
    
    obj.location = location
    if material:
        obj.data.materials.append(material)
    
    return obj

def main():
    # Create/clear collection
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if coll:
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj)
    else:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)
    
    count = 0
    
    # Find survey points
    for obj in bpy.data.objects:
        # Look for IFC annotations or survey objects
        is_survey = (
            "Survey" in obj.name or 
            "IfcAnnotation" in obj.name or
            obj.name.startswith("Survey_Point_")
        )
        
        if is_survey:
            loc = obj.matrix_world.translation.copy()
            
            # Extract info from name
            point_id = obj.name.split('_')[-1] if '_' in obj.name else str(count+1)
            
            # Try to get survey code from custom properties
            code = 'DEFAULT'
            description = ''
            
            # Check various property locations
            if 'Survey_Code' in obj:
                code = obj['Survey_Code']
            if 'Survey_Description' in obj:
                description = obj['Survey_Description']
            
            # Get or create material
            mat_name = f"Survey_{code}"
            material = bpy.data.materials.get(mat_name)
            if not material:
                color = COLORS.get(code, COLORS['DEFAULT'])
                material = create_material(mat_name, color)
            
            # Create sphere marker
            sphere = create_sphere(f"Marker_{point_id}", loc, SPHERE_RADIUS, material)
            sphere.parent = obj
            coll.objects.link(sphere)
            
            # Create label
            if MAKE_LABELS:
                curve = bpy.data.curves.new(f"Label_{point_id}", 'FONT')
                curve.size = LABEL_SIZE
                label_obj = bpy.data.objects.new(f"Label_{point_id}", curve)
                
                # Set label text
                label_text = point_id
                if description:
                    label_text += f"\n{description}"
                if code != 'DEFAULT':
                    label_text += f"\n[{code}]"
                
                curve.body = label_text
                
                # Position label
                label_obj.location = (
                    loc.x + LABEL_OFFSET[0],
                    loc.y + LABEL_OFFSET[1],
                    loc.z + LABEL_OFFSET[2]
                )
                label_obj.parent = obj
                coll.objects.link(label_obj)
            
            count += 1
            print(f"Visualized: {point_id} [{code}] at {loc}")
    
    print(f"\n✅ Created {count} survey point visualizations!")
    
    # Set viewport to solid shading
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'
                    space.shading.color_type = 'MATERIAL'
    
    return count

# Run the script
if __name__ == "__main__":
    result = main()
    if result == 0:
        print("⚠️  No survey points found!")
        print("Make sure you've imported the IFC file with Bonsai first.")