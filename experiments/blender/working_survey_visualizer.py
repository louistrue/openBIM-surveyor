"""
Working Survey Point Visualizer for Blender + Bonsai
Simplified version that works with current Bonsai API
"""

import bpy
import bmesh
from mathutils import Vector

def create_survey_visualization():
    """Create visual markers for survey points"""
    print("🚀 Creating Survey Point Visualization...")
    
    # Settings
    SPHERE_RADIUS = 0.3
    LABEL_SIZE = 0.25
    LABEL_OFFSET = Vector((0, 0, 0.6))
    
    # Create collection
    collection_name = "Survey_Visualization"
    if collection_name in bpy.data.collections:
        # Clear existing
        coll = bpy.data.collections[collection_name]
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        coll = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(coll)
    
    # Create materials
    # Red material for VAG_VM points
    if "Survey_VAG_VM" not in bpy.data.materials:
        mat_red = bpy.data.materials.new("Survey_VAG_VM")
        mat_red.use_nodes = True
        mat_red.diffuse_color = (1.0, 0.2, 0.2, 1.0)  # Red
        # Add emission for visibility
        nodes = mat_red.node_tree.nodes
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs[0].default_value = (1.0, 0.3, 0.3, 1.0)
        emission.inputs[1].default_value = 0.8
        output = nodes.get('Material Output')
        mat_red.node_tree.links.new(emission.outputs[0], output.inputs[0])
    
    # Yellow material for labels
    if "Survey_Label" not in bpy.data.materials:
        mat_label = bpy.data.materials.new("Survey_Label")
        mat_label.use_nodes = True
        mat_label.diffuse_color = (1.0, 1.0, 0.0, 1.0)  # Yellow
        nodes = mat_label.node_tree.nodes
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs[0].default_value = (1.0, 1.0, 0.2, 1.0)
        emission.inputs[1].default_value = 1.0
        output = nodes.get('Material Output')
        mat_label.node_tree.links.new(emission.outputs[0], output.inputs[0])
    
    # Find survey objects
    survey_objects = []
    for obj in bpy.context.scene.objects:
        # Look for objects that might be survey points
        if (obj.name.startswith('Survey_Point_') or 
            'Survey' in obj.name or
            'IfcAnnotation' in obj.name or
            'IfcBuildingElementProxy' in obj.name):
            survey_objects.append(obj)
    
    print(f"📊 Found {len(survey_objects)} potential survey objects")
    
    if not survey_objects:
        print("❌ No survey objects found!")
        return False
    
    # Process each object
    created_count = 0
    for i, obj in enumerate(survey_objects):
        try:
            # Get object location
            location = obj.matrix_world.translation.copy()
            
            # Extract point ID from name
            if 'Survey_Point_' in obj.name:
                point_id = obj.name.split('Survey_Point_')[-1]
            else:
                point_id = str(i + 1)
            
            # Get description if available
            description = ""
            if hasattr(obj, 'BIMObjectProperties'):
                try:
                    # Try to get IFC entity info
                    if hasattr(obj.BIMObjectProperties, 'ifc_definition_id'):
                        # We have an IFC object, but can't access properties easily
                        # So we'll use the object name and location
                        pass
                except:
                    pass
            
            # Create sphere marker
            bpy.ops.mesh.primitive_uv_sphere_add(radius=SPHERE_RADIUS, location=location)
            sphere = bpy.context.active_object
            sphere.name = f"SurveyMarker_{point_id}"
            
            # Apply red material
            sphere.data.materials.append(bpy.data.materials["Survey_VAG_VM"])
            
            # Move to collection
            for c in sphere.users_collection:
                c.objects.unlink(sphere)
            coll.objects.link(sphere)
            
            # Create text label
            bpy.ops.object.text_add(location=location + LABEL_OFFSET)
            label = bpy.context.active_object
            label.name = f"SurveyLabel_{point_id}"
            label.data.body = f"Point {point_id}"
            label.data.size = LABEL_SIZE
            label.data.align_x = 'CENTER'
            label.data.align_y = 'BOTTOM'
            
            # Apply yellow material to label
            label.data.materials.append(bpy.data.materials["Survey_Label"])
            
            # Move label to collection
            for c in label.users_collection:
                c.objects.unlink(label)
            coll.objects.link(label)
            
            created_count += 1
            print(f"✅ Created marker for Survey Point {point_id} at {location}")
            
        except Exception as e:
            print(f"❌ Error processing {obj.name}: {e}")
            continue
    
    print(f"\n🎉 Successfully created {created_count} survey point visualizations!")
    
    # Set viewport shading to material preview
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'MATERIAL'
                        break
                break
    except:
        print("Could not set viewport shading")
    
    # Select all created markers
    bpy.ops.object.select_all(action='DESELECT')
    for obj in coll.objects:
        if obj.name.startswith('SurveyMarker_'):
            obj.select_set(True)
    
    print("\n📋 Visualization Complete!")
    print(f"   🔴 {created_count} red spheres mark survey points")
    print(f"   🏷️  {created_count} yellow labels show point IDs")
    print(f"   📁 All organized in '{collection_name}' collection")
    print("\n🎯 Next Steps:")
    print("   1. Use these spheres as snap targets")
    print("   2. Model your roads, terraces, utilities")
    print("   3. Assign IFC classes to new elements")
    
    return True

def clear_visualization():
    """Clear existing survey visualization"""
    collection_name = "Survey_Visualization"
    if collection_name in bpy.data.collections:
        coll = bpy.data.collections[collection_name]
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(coll)
        print("🧹 Cleared existing visualization")

def main():
    """Main execution function"""
    try:
        # Clear any existing visualization
        clear_visualization()
        
        # Create new visualization
        success = create_survey_visualization()
        
        if success:
            print("\n✅ Survey Point Visualization SUCCESS!")
        else:
            print("\n❌ No survey points found to visualize")
            print("   Make sure you've imported the IFC file with survey points")
        
        return success
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

# Execute when run
if __name__ == "__main__":
    main()