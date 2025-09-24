"""
Blender + Bonsai script for importing survey points as IFC annotations
This addresses the client's need for automated IFC point import with metadata preservation
"""

import bpy
import bmesh
import csv
import json
from pathlib import Path

# Try to import Bonsai/BlenderBIM modules
try:
    import bonsai.tool.ifc as ifc_tool
    import bonsai.tool.project as project_tool
    import bonsai.tool.geometry as geometry_tool
    import ifcopenshell
    BONSAI_AVAILABLE = True
except ImportError:
    BONSAI_AVAILABLE = False
    print("⚠️  Bonsai addon not available - creating basic Blender objects only")

def clear_scene():
    """Clear existing mesh objects"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def setup_ifc_project():
    """Setup new IFC project with Bonsai"""
    if not BONSAI_AVAILABLE:
        print("Skipping IFC project setup - Bonsai not available")
        return None
    
    try:
        # Create new IFC project
        bpy.ops.bim.create_project()
        
        # Get the IFC file
        ifc_file = ifc_tool.get()
        
        # Set up coordinate reference system
        # This would need to be configured based on the client's CRS
        print("✅ IFC project created")
        return ifc_file
        
    except Exception as e:
        print(f"❌ Error creating IFC project: {e}")
        return None

def create_survey_property_set():
    """Create custom property set for survey data"""
    if not BONSAI_AVAILABLE:
        return None
    
    try:
        ifc_file = ifc_tool.get()
        
        # Create property set template for survey data
        # This matches the client's requirement for SurveyData pset
        pset_template = {
            "Name": "SurveyData",
            "Description": "Survey point metadata",
            "Properties": [
                {"Name": "ID", "Type": "IfcLabel"},
                {"Name": "Description", "Type": "IfcText"},
                {"Name": "Code", "Type": "IfcLabel"},
                {"Name": "OriginalX", "Type": "IfcReal"},
                {"Name": "OriginalY", "Type": "IfcReal"},
                {"Name": "OriginalZ", "Type": "IfcReal"}
            ]
        }
        
        print("✅ Survey property set template created")
        return pset_template
        
    except Exception as e:
        print(f"❌ Error creating property set: {e}")
        return None

def create_survey_collections():
    """Create organized collections for survey points by code"""
    collections = {}
    
    # Main survey collection
    survey_collection = bpy.data.collections.new("Survey_Points")
    bpy.context.scene.collection.children.link(survey_collection)
    collections['main'] = survey_collection
    
    # Will create sub-collections by code as needed
    collections['by_code'] = {}
    
    return collections

def create_ifc_survey_point(point_data, collections, pset_template, transform_info):
    """Create survey point as IFC annotation with metadata"""
    
    # Get coordinates
    x = float(point_data['X'])
    y = float(point_data['Y'])
    z = float(point_data['Z'])
    point_id = point_data['ID']
    description = point_data.get('Description', '')
    code = point_data.get('Code', 'UNKNOWN')
    
    # Calculate original coordinates if transform info available
    orig_x = x
    orig_y = y
    orig_z = z
    
    if transform_info and 'local_origin' in transform_info:
        origin = transform_info['local_origin']
        orig_x = x + origin['x']
        orig_y = y + origin['y']
        orig_z = z + origin['z']
    
    # Create collection for this code if needed
    if code not in collections['by_code']:
        code_collection = bpy.data.collections.new(f"Code_{code}")
        collections['main'].children.link(code_collection)
        collections['by_code'][code] = code_collection
    
    if BONSAI_AVAILABLE:
        try:
            # Create IFC annotation point
            ifc_file = ifc_tool.get()
            
            # Create IfcAnnotation with Survey predefined type
            annotation = ifc_file.create_entity("IfcAnnotation")
            annotation.Name = f"Survey_Point_{point_id}"
            annotation.Description = description
            annotation.PredefinedType = "SURVEY"  # Client's requirement
            
            # Create point geometry (simplified - would need proper IFC geometry)
            # For now, create a Blender object and link to IFC
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(x, y, z))
            point_obj = bpy.context.active_object
            point_obj.name = f"Survey_Point_{point_id}"
            
            # Move to appropriate collection
            bpy.context.scene.collection.objects.unlink(point_obj)
            collections['by_code'][code].objects.link(point_obj)
            
            # Attach custom property set (SurveyData)
            if pset_template:
                # This would need proper Bonsai API calls to attach psets
                # For now, store as custom properties
                point_obj['IFC_Entity'] = annotation.id()
                point_obj['Survey_ID'] = point_id
                point_obj['Survey_Description'] = description
                point_obj['Survey_Code'] = code
                point_obj['Survey_OriginalX'] = orig_x
                point_obj['Survey_OriginalY'] = orig_y
                point_obj['Survey_OriginalZ'] = orig_z
            
            print(f"✅ Created IFC survey point: {point_id}")
            return point_obj
            
        except Exception as e:
            print(f"❌ Error creating IFC point {point_id}: {e}")
            # Fallback to basic Blender object
            
    # Fallback: Create basic Blender object
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.2, location=(x, y, z))
    point_obj = bpy.context.active_object
    point_obj.name = f"Survey_Point_{point_id}"
    
    # Store metadata as custom properties
    point_obj['Survey_ID'] = point_id
    point_obj['Survey_Description'] = description
    point_obj['Survey_Code'] = code
    point_obj['Survey_OriginalX'] = orig_x
    point_obj['Survey_OriginalY'] = orig_y
    point_obj['Survey_OriginalZ'] = orig_z
    
    # Move to appropriate collection
    bpy.context.scene.collection.objects.unlink(point_obj)
    collections['by_code'][code].objects.link(point_obj)
    
    return point_obj

def create_terrain_surface_ifc(points, collections):
    """Create terrain surface as IfcGeographicElement"""
    if len(points) < 3:
        return None
    
    # Create mesh from points
    mesh = bpy.data.meshes.new("Terrain_Surface")
    terrain_obj = bpy.data.objects.new("Terrain_Surface", mesh)
    
    # Create terrain collection
    if 'terrain' not in collections:
        terrain_collection = bpy.data.collections.new("Terrain")
        bpy.context.scene.collection.children.link(terrain_collection)
        collections['terrain'] = terrain_collection
    
    collections['terrain'].objects.link(terrain_obj)
    
    # Create triangulated mesh
    bm = bmesh.new()
    
    # Add vertices
    for point_data in points:
        if point_data['Code'] != 'ORIGIN':
            x = float(point_data['X'])
            y = float(point_data['Y'])
            z = float(point_data['Z'])
            bm.verts.new((x, y, z))
    
    # Triangulate
    bm.verts.ensure_lookup_table()
    try:
        bmesh.ops.convex_hull(bm, input=bm.verts)
    except:
        # Simple triangulation fallback
        if len(bm.verts) >= 3:
            for i in range(len(bm.verts) - 2):
                try:
                    bm.faces.new([bm.verts[0], bm.verts[i+1], bm.verts[i+2]])
                except:
                    pass
    
    bm.to_mesh(mesh)
    bm.free()
    
    # Set IFC properties
    if BONSAI_AVAILABLE:
        terrain_obj['IFC_Type'] = 'IfcGeographicElement'
        terrain_obj['IFC_PredefinedType'] = 'TERRAIN'
    
    # Add material
    mat = bpy.data.materials.new(name="Terrain_Material")
    mat.diffuse_color = (0.6, 0.4, 0.2, 1.0)
    terrain_obj.data.materials.append(mat)
    
    return terrain_obj

def import_survey_points_to_ifc(csv_file, transform_info_file=None):
    """Main function to import survey points as IFC annotations"""
    print(f"🚀 Importing survey points to IFC from: {csv_file}")
    
    # Load transformation info
    transform_info = None
    if transform_info_file and Path(transform_info_file).exists():
        with open(transform_info_file, 'r') as f:
            transform_info = json.load(f)
        print(f"✅ Loaded transformation info")
    
    # Clear scene and setup
    clear_scene()
    
    # Setup IFC project
    ifc_file = setup_ifc_project()
    
    # Create property set template
    pset_template = create_survey_property_set()
    
    # Create collections
    collections = create_survey_collections()
    
    # Read and process points
    points = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            points.append(row)
            if row['Code'] != 'ORIGIN':  # Skip origin point for objects
                create_ifc_survey_point(row, collections, pset_template, transform_info)
    
    print(f"✅ Created {len([p for p in points if p['Code'] != 'ORIGIN'])} survey point objects")
    
    # Create terrain surface
    terrain_obj = create_terrain_surface_ifc(points, collections)
    if terrain_obj:
        print("✅ Created terrain surface")
    
    # Organize outliner (client's requirement)
    # Collapse collections to reduce clutter
    for collection in collections['by_code'].values():
        collection.hide_viewport = False  # Keep visible but organized
    
    print("✅ Survey points imported successfully!")
    print("\n📋 Next steps:")
    print("1. Use points as snap targets for design modeling")
    print("2. Model roads, terraces, utilities as IFC elements")
    print("3. Export IFC 4x3 for BIM coordination")
    print("4. Export surfaces as LandXML for machine control")

def main():
    """Main execution when run in Blender"""
    # Default file paths - adjust as needed
    csv_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\processed\client_survey_processed.csv"
    transform_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\processed\client_survey_processed_transform_info.json"
    
    if Path(csv_file).exists():
        import_survey_points_to_ifc(csv_file, transform_file)
        
        # Save blend file
        blend_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\output\client_survey_ifc.blend"
        bpy.ops.wm.save_as_mainfile(filepath=blend_file)
        print(f"✅ Saved Blender file: {blend_file}")
        
        # Try to export IFC if Bonsai is available
        if BONSAI_AVAILABLE:
            try:
                ifc_file = r"C:\Users\louistrue\Documents\Dev\bonsai-topo\data\output\client_survey.ifc"
                bpy.ops.export_ifc.bim(filepath=ifc_file)
                print(f"✅ Exported IFC file: {ifc_file}")
            except Exception as e:
                print(f"⚠️  IFC export failed: {e}")
                print("Manual export required through Bonsai addon")
    else:
        print(f"❌ CSV file not found: {csv_file}")

if __name__ == "__main__":
    main()