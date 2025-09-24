"""
Blender script to visualize invisible IFC survey points
Creates visible markers and labels for IfcAnnotation objects imported via Bonsai
Run this script in Blender after importing the IFC file with survey points
"""

import bpy
import bmesh
from mathutils import Vector

# Settings / Einstellungen
COLLECTION_NAME = "Survey Points Visualization"
EMPTY_DISPLAY   = 'SPHERE'      # 'PLAIN_AXES', 'ARROWS', 'CUBE', 'SPHERE', 'CONE'
EMPTY_SIZE      = 0.5           # Marker size
MAKE_LABELS     = True          # Show name as text object
LABEL_OFFSET    = (0.3, 0.3, 0.2)  # Label position offset
LABEL_SIZE      = 0.25          # Text size
CREATE_MESH_SPHERES = True      # Create actual mesh spheres instead of empties
SPHERE_RADIUS   = 0.15          # Mesh sphere radius
COLOR_BY_CODE   = True          # Color code survey points

# Color mapping for different survey codes
CODE_COLORS = {
    'VAG_VM': (1.0, 0.2, 0.2, 1.0),    # Red for VAG_VM
    'CORNER': (0.2, 1.0, 0.2, 1.0),    # Green for corners
    'TREE': (0.2, 0.8, 0.2, 1.0),      # Green for trees
    'BUILDING': (0.8, 0.8, 0.2, 1.0),  # Yellow for buildings
    'ROAD': (0.5, 0.5, 0.5, 1.0),      # Gray for roads
    'UTILITY': (0.2, 0.2, 1.0, 1.0),   # Blue for utilities
    'DEFAULT': (1.0, 1.0, 1.0, 1.0)    # White for unknown
}

def get_survey_data_from_object(obj):
    """Extract survey data from IFC object custom properties"""
    survey_data = {}
    
    # Try to get survey data from custom properties
    if hasattr(obj, 'BIMObjectProperties') and obj.BIMObjectProperties:
        # Bonsai stores IFC properties here
        for prop_set in obj.BIMObjectProperties.psets:
            if prop_set.name == "SurveyData":
                for prop in prop_set.properties:
                    survey_data[prop.name] = prop.string_value or prop.float_value
    
    # Fallback: try direct custom properties
    for key in ['Survey_ID', 'Survey_Code', 'Survey_Description', 'LocalX', 'LocalY', 'LocalZ']:
        if key in obj:
            survey_data[key.replace('Survey_', '')] = obj[key]
    
    return survey_data

def create_material_for_code(code):
    """Create or get material for survey point code"""
    mat_name = f"SurveyPoint_{code}"
    mat = bpy.data.materials.get(mat_name)
    
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True
        
        # Get color for this code
        color = CODE_COLORS.get(code, CODE_COLORS['DEFAULT'])
        
        # Set material color
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs[0].default_value = color  # Base Color
            bsdf.inputs[7].default_value = 0.8    # Roughness
            bsdf.inputs[15].default_value = 1.0   # Transmission (make it glow slightly)
    
    return mat

def create_mesh_sphere(name, location, radius=0.15):
    """Create a mesh sphere at the given location"""
    # Create mesh
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    
    # Create sphere geometry
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=radius)
    bm.to_mesh(mesh)
    bm.free()
    
    # Set location
    obj.location = location
    
    return obj

def create_survey_point_visualization():
    """Main function to create survey point visualizations"""
    
    # Prepare collection
    coll = bpy.data.collections.get(COLLECTION_NAME)
    if not coll:
        coll = bpy.data.collections.new(COLLECTION_NAME)
        bpy.context.scene.collection.children.link(coll)
    else:
        # Clear existing objects in collection
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    
    count = 0
    survey_points_found = []
    
    # Look for IFC annotation objects
    for obj in bpy.data.objects:
        # Check for Bonsai/BlenderBIM imported survey points
        is_survey_point = False
        survey_data = {}
        
        # Method 1: Check object name patterns
        if (obj.name.startswith("IfcAnnotation/Survey_Point_") or 
            obj.name.startswith("Survey_Point_") or
            "Survey" in obj.name):
            is_survey_point = True
            
        # Method 2: Check IFC class and predefined type
        if hasattr(obj, 'BIMObjectProperties') and obj.BIMObjectProperties:
            if (obj.BIMObjectProperties.ifc_definition_id and 
                "Annotation" in str(obj.BIMObjectProperties.ifc_definition_id)):
                is_survey_point = True
        
        # Method 3: Check custom properties for survey data
        survey_data = get_survey_data_from_object(obj)
        if survey_data:
            is_survey_point = True
        
        if is_survey_point:
            # Get world position of the IFC object
            loc = obj.matrix_world.translation.copy()
            
            # Extract point info
            point_id = survey_data.get('ID', obj.name.split('_')[-1])
            point_code = survey_data.get('Code', 'UNKNOWN')
            point_desc = survey_data.get('Description', '')
            
            print(f"Found survey point: {point_id} at {loc} with code {point_code}")
            
            # Create visualization marker
            if CREATE_MESH_SPHERES:
                marker = create_mesh_sphere(f"SurveyMarker_{point_id}", loc, SPHERE_RADIUS)
                
                # Apply material based on code
                if COLOR_BY_CODE:
                    material = create_material_for_code(point_code)
                    marker.data.materials.append(material)
                
            else:
                # Create empty as marker
                marker = bpy.data.objects.new(f"SurveyMarker_{point_id}", None)
                marker.empty_display_type = EMPTY_DISPLAY
                marker.empty_display_size = EMPTY_SIZE
                marker.location = loc
            
            # Parent to original object so it moves together
            marker.parent = obj
            
            # Add to collection
            coll.objects.link(marker)
            
            # Create label with survey information
            if MAKE_LABELS:
                curve = bpy.data.curves.new(f"SurveyLabel_{point_id}", 'FONT')
                curve.size = LABEL_SIZE
                curve.align_x = 'LEFT'
                curve.align_y = 'BOTTOM'
                
                label = bpy.data.objects.new(f"SurveyLabel_{point_id}", curve)
                
                # Create label text with survey info
                label_text = f"{point_id}"
                if point_desc and point_desc != point_id:
                    label_text += f"\n{point_desc}"
                if point_code and point_code != 'UNKNOWN':
                    label_text += f"\n[{point_code}]"
                
                label.data.body = label_text
                
                # Position label with offset
                label.location = (
                    loc[0] + LABEL_OFFSET[0],
                    loc[1] + LABEL_OFFSET[1], 
                    loc[2] + LABEL_OFFSET[2]
                )
                
                # Parent to original object
                label.parent = obj
                
                # Add to collection
                coll.objects.link(label)
                
                # Create label material
                if not label.data.materials:
                    label_mat = bpy.data.materials.new(f"SurveyLabel_Material")
                    label_mat.use_nodes = True
                    bsdf = label_mat.node_tree.nodes.get("Principled BSDF")
                    if bsdf:
                        bsdf.inputs[0].default_value = (1.0, 1.0, 0.0, 1.0)  # Yellow text
                        bsdf.inputs[19].default_value = 1.0  # Emission strength
                    label.data.materials.append(label_mat)
            
            survey_points_found.append({
                'id': point_id,
                'code': point_code,
                'description': point_desc,
                'location': loc,
                'object': obj
            })
            
            count += 1
    
    # Create summary report
    print(f"\n=== Survey Point Visualization Report ===")
    print(f"Created: {count} markers{' with labels' if MAKE_LABELS else ''} in '{COLLECTION_NAME}'")
    
    if survey_points_found:
        print(f"\nSurvey Points Found:")
        codes = {}
        for point in survey_points_found:
            code = point['code']
            if code not in codes:
                codes[code] = 0
            codes[code] += 1
            print(f"  {point['id']}: {point['description']} [{point['code']}]")
        
        print(f"\nSummary by Code:")
        for code, count_code in codes.items():
            print(f"  {code}: {count_code} points")
    
    # Set viewport shading to solid for better visibility
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'
                    space.shading.color_type = 'MATERIAL'
    
    # Focus on survey points if any were found
    if survey_points_found and bpy.context.view_layer.objects:
        # Select all survey markers
        bpy.ops.object.select_all(action='DESELECT')
        for obj in coll.objects:
            if obj.name.startswith("SurveyMarker_"):
                obj.select_set(True)
                bpy.context.view_layer.objects.active = obj
        
        # Frame selected objects
        if bpy.context.selected_objects:
            bpy.ops.view3d.view_selected()
    
    return count

# Main execution
if __name__ == "__main__":
    print("🚀 Starting Survey Point Visualization...")
    
    # Check if we're in Blender
    try:
        import bpy
        count = create_survey_point_visualization()
        
        if count > 0:
            print(f"✅ Successfully created visualization for {count} survey points!")
            print(f"📁 Check the '{COLLECTION_NAME}' collection in the outliner")
            print(f"🎯 Survey points are now visible as {'mesh spheres' if CREATE_MESH_SPHERES else 'empties'}")
            if COLOR_BY_CODE:
                print(f"🎨 Points are color-coded by survey code")
        else:
            print("⚠️  No survey points found!")
            print("   Make sure you have imported the IFC file with Bonsai addon first")
            print("   Look for objects with names containing 'Survey' or 'IfcAnnotation'")
            
    except ImportError:
        print("❌ This script must be run inside Blender")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()