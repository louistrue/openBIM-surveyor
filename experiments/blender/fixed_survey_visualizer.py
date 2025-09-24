"""
Fixed Survey Point Visualizer for Blender + Bonsai
Works with current Bonsai API to visualize IFC survey points
"""

import bpy
import bmesh
from mathutils import Vector

def get_survey_data_from_object(obj):
    """Extract survey data from IFC object using current Bonsai API"""
    survey_data = {
        'id': 'Unknown',
        'description': '',
        'code': 'Unknown',
        'local_coords': (0, 0, 0),
        'original_coords': (0, 0, 0)
    }
    
    try:
        # Try to get BIM properties
        if hasattr(obj, 'BIMObjectProperties'):
            bim_props = obj.BIMObjectProperties
            
            # Get IFC entity if available
            if hasattr(bim_props, 'ifc_definition_id') and bim_props.ifc_definition_id:
                try:
                    import bonsai.tool.ifc as ifc_tool
                    ifc_file = ifc_tool.get()
                    
                    if ifc_file:
                        entity = ifc_file.by_id(bim_props.ifc_definition_id)
                        
                        # Get basic info from entity
                        if hasattr(entity, 'Name') and entity.Name:
                            survey_data['id'] = entity.Name.replace('Survey_Point_', '')
                        
                        if hasattr(entity, 'Description') and entity.Description:
                            survey_data['description'] = entity.Description
                        
                        # Try to get property sets using current API
                        try:
                            import bonsai.tool.pset as pset_tool
                            psets = pset_tool.get_element_psets(entity)
                            
                            if 'SurveyData' in psets:
                                survey_pset = psets['SurveyData']
                                
                                survey_data['id'] = survey_pset.get('ID', survey_data['id'])
                                survey_data['description'] = survey_pset.get('Description', survey_data['description'])
                                survey_data['code'] = survey_pset.get('Code', 'Unknown')
                                
                                # Get coordinates
                                local_x = survey_pset.get('LocalX', 0)
                                local_y = survey_pset.get('LocalY', 0)
                                local_z = survey_pset.get('LocalZ', 0)
                                survey_data['local_coords'] = (local_x, local_y, local_z)
                                
                                orig_x = survey_pset.get('OriginalX', 0)
                                orig_y = survey_pset.get('OriginalY', 0)
                                orig_z = survey_pset.get('OriginalZ', 0)
                                survey_data['original_coords'] = (orig_x, orig_y, orig_z)
                        
                        except Exception as e:
                            print(f"Could not get property sets: {e}")
                
                except Exception as e:
                    print(f"Could not access IFC entity: {e}")
        
        # Fallback: try to get data from object name and location
        if survey_data['id'] == 'Unknown' and obj.name.startswith('Survey_Point_'):
            survey_data['id'] = obj.name.replace('Survey_Point_', '')
        
        # Get location from object
        if obj.location:
            survey_data['local_coords'] = tuple(obj.location)
    
    except Exception as e:
        print(f"Error extracting survey data from {obj.name}: {e}")
    
    return survey_data

def create_survey_point_visualization(obj, survey_data):
    """Create visual representation of survey point"""
    
    # Create a small sphere at the survey point location
    location = Vector(survey_data['local_coords'])
    
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=location)
    sphere = bpy.context.active_object
    sphere.name = f"Visual_Survey_{survey_data['id']}"
    
    # Create material based on code
    code = survey_data['code']
    material_name = f"Survey_{code}"
    
    if material_name not in bpy.data.materials:
        mat = bpy.data.materials.new(name=material_name)
        mat.use_nodes = True
        
        # Set color based on code
        if code == 'VAG_VM':
            mat.diffuse_color = (1.0, 0.2, 0.2, 1.0)  # Red for VAG_VM
        else:
            mat.diffuse_color = (0.2, 0.8, 0.2, 1.0)  # Green for others
        
        # Set emission for visibility
        if mat.node_tree:
            emission = mat.node_tree.nodes.new('ShaderNodeEmission')
            emission.inputs[0].default_value = mat.diffuse_color
            emission.inputs[1].default_value = 0.5  # Emission strength
            
            output = mat.node_tree.nodes.get('Material Output')
            if output:
                mat.node_tree.links.new(emission.outputs[0], output.inputs[0])
    
    else:
        mat = bpy.data.materials[material_name]
    
    # Assign material
    if sphere.data.materials:
        sphere.data.materials[0] = mat
    else:
        sphere.data.materials.append(mat)
    
    # Add text label
    bpy.ops.object.text_add(location=location + Vector((0, 0, 0.5)))
    text_obj = bpy.context.active_object
    text_obj.name = f"Label_Survey_{survey_data['id']}"
    text_obj.data.body = f"{survey_data['id']}\n{survey_data['description']}"
    text_obj.data.size = 0.2
    text_obj.data.align_x = 'CENTER'
    text_obj.data.align_y = 'CENTER'
    
    # Create text material
    if "Survey_Text" not in bpy.data.materials:
        text_mat = bpy.data.materials.new(name="Survey_Text")
        text_mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)  # White text
    else:
        text_mat = bpy.data.materials["Survey_Text"]
    
    if text_obj.data.materials:
        text_obj.data.materials[0] = text_mat
    else:
        text_obj.data.materials.append(text_mat)
    
    return sphere, text_obj

def create_survey_collections():
    """Create organized collections for survey visualization"""
    collections = {}
    
    # Main collection
    if "Survey_Visualization" not in bpy.data.collections:
        main_collection = bpy.data.collections.new("Survey_Visualization")
        bpy.context.scene.collection.children.link(main_collection)
    else:
        main_collection = bpy.data.collections["Survey_Visualization"]
    
    collections['main'] = main_collection
    
    # Sub-collections
    for sub_name in ['Points', 'Labels', 'Original_IFC']:
        collection_name = f"Survey_{sub_name}"
        if collection_name not in bpy.data.collections:
            sub_collection = bpy.data.collections.new(collection_name)
            main_collection.children.link(sub_collection)
        else:
            sub_collection = bpy.data.collections[collection_name]
        
        collections[sub_name.lower()] = sub_collection
    
    return collections

def move_object_to_collection(obj, collection):
    """Move object to specific collection"""
    # Remove from all collections
    for coll in obj.users_collection:
        coll.objects.unlink(obj)
    
    # Add to target collection
    collection.objects.link(obj)

def visualize_all_survey_points():
    """Main function to visualize all survey points in the scene"""
    print("🚀 Starting Survey Point Visualization...")
    
    try:
        # Create collections
        collections = create_survey_collections()
        
        # Find all IFC annotation objects
        survey_objects = []
        for obj in bpy.context.scene.objects:
            if (obj.name.startswith('Survey_Point_') or 
                (hasattr(obj, 'BIMObjectProperties') and 
                 hasattr(obj.BIMObjectProperties, 'ifc_definition_id'))):
                survey_objects.append(obj)
        
        if not survey_objects:
            print("❌ No survey point objects found in scene")
            print("   Make sure you've imported the IFC file with survey points")
            return False
        
        print(f"📊 Found {len(survey_objects)} survey objects")
        
        # Process each survey object
        visualized_count = 0
        for obj in survey_objects:
            try:
                # Get survey data
                survey_data = get_survey_data_from_object(obj)
                
                print(f"Processing Survey Point {survey_data['id']}: {survey_data['description']}")
                
                # Create visualization
                sphere, label = create_survey_point_visualization(obj, survey_data)
                
                # Organize in collections
                move_object_to_collection(sphere, collections['points'])
                move_object_to_collection(label, collections['labels'])
                move_object_to_collection(obj, collections['original_ifc'])
                
                visualized_count += 1
                
            except Exception as e:
                print(f"❌ Error processing {obj.name}: {e}")
                continue
        
        print(f"✅ Successfully visualized {visualized_count} survey points")
        
        # Set viewport shading
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
        
        # Frame all objects
        bpy.ops.view3d.view_all()
        
        print("🎉 Survey point visualization completed!")
        print("\n📋 What you should see:")
        print("   🔴 Red spheres: VAG_VM survey points")
        print("   🏷️  White labels: Point IDs and descriptions")
        print("   📁 Organized collections in outliner")
        print("\n📚 Next steps:")
        print("   1. Use these points as snap targets")
        print("   2. Model roads, terraces, utilities")
        print("   3. Assign proper IFC classes to new elements")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def clear_survey_visualization():
    """Clear existing survey visualization"""
    print("🧹 Clearing existing survey visualization...")
    
    # Remove visualization objects
    objects_to_remove = []
    for obj in bpy.context.scene.objects:
        if (obj.name.startswith('Visual_Survey_') or 
            obj.name.startswith('Label_Survey_')):
            objects_to_remove.append(obj)
    
    for obj in objects_to_remove:
        bpy.data.objects.remove(obj, do_unlink=True)
    
    # Remove collections
    collections_to_remove = []
    for coll in bpy.data.collections:
        if coll.name.startswith('Survey_'):
            collections_to_remove.append(coll)
    
    for coll in collections_to_remove:
        bpy.data.collections.remove(coll)
    
    print(f"✅ Removed {len(objects_to_remove)} objects and {len(collections_to_remove)} collections")

# Main execution
if __name__ == "__main__":
    # Clear existing visualization
    clear_survey_visualization()
    
    # Create new visualization
    visualize_all_survey_points()