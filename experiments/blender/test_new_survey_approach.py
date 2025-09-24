"""
Test the new survey point approach using IfcBuildingElementProxy with sphere geometry
This should be more viewer-friendly than IfcAnnotation
"""

import bpy
import bmesh
from mathutils import Vector

def test_survey_import():
    """Test importing and visualizing the new survey point approach"""
    print("🚀 Testing New Survey Point Approach...")
    
    # Clear existing scene
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    
    # Import IFC file
    ifc_file = "data/output/client_survey.ifc"
    
    try:
        # Import using Bonsai
        bpy.ops.bim.load_project(filepath=ifc_file)
        print(f"✅ Imported IFC file: {ifc_file}")
    except Exception as e:
        print(f"❌ Failed to import IFC: {e}")
        return False
    
    # Find survey objects
    survey_objects = []
    for obj in bpy.context.scene.objects:
        # Look for our new IfcBuildingElementProxy survey points
        if (obj.name.startswith('Survey_Point_') or 
            'Survey' in obj.name or
            'IfcBuildingElementProxy' in obj.name):
            survey_objects.append(obj)
            print(f"📍 Found survey object: {obj.name} at {obj.location}")
    
    print(f"📊 Found {len(survey_objects)} survey objects")
    
    if not survey_objects:
        print("❌ No survey objects found!")
        print("Available objects:")
        for obj in bpy.context.scene.objects:
            print(f"  - {obj.name} ({obj.type})")
        return False
    
    # Check if they have geometry
    geometry_count = 0
    for obj in survey_objects:
        if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 0:
            geometry_count += 1
            print(f"✅ {obj.name} has {len(obj.data.vertices)} vertices")
        else:
            print(f"⚠️  {obj.name} has no mesh geometry")
    
    print(f"📐 {geometry_count}/{len(survey_objects)} objects have visible geometry")
    
    # Set viewport to solid shading
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
                        break
                break
    except:
        print("Could not set viewport shading")
    
    # Focus on survey points
    if survey_objects:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in survey_objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = survey_objects[0]
        bpy.ops.view3d.view_selected()
    
    print(f"\n🎉 Test completed!")
    print(f"   📍 {len(survey_objects)} survey points imported")
    print(f"   📐 {geometry_count} have visible geometry")
    print(f"   🎯 Viewport focused on survey points")
    
    return len(survey_objects) > 0 and geometry_count > 0

def main():
    """Main test function"""
    try:
        success = test_survey_import()
        
        if success:
            print("\n✅ NEW SURVEY APPROACH SUCCESS!")
            print("   IfcBuildingElementProxy with sphere geometry works!")
        else:
            print("\n❌ Test failed - survey points not visible")
        
        return success
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False

# Execute when run
if __name__ == "__main__":
    main()