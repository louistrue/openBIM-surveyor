#!/usr/bin/env python3
"""
Simple CSV to IFC 4x3 converter
Creates basic IfcAnnotation objects with SurveyData property sets
Focuses on core functionality with proper georeferencing
"""

import csv
import json
import logging
from pathlib import Path
from datetime import datetime

try:
    import ifcopenshell
    import ifcopenshell.guid
    IFCOPENSHELL_AVAILABLE = True
except ImportError:
    IFCOPENSHELL_AVAILABLE = False
    print("❌ IfcOpenShell not available - install with: pip install ifcopenshell")

def create_basic_ifc_with_survey_points(csv_file, output_file, transform_info=None):
    """Create basic IFC file with survey points as annotations"""
    
    if not IFCOPENSHELL_AVAILABLE:
        print("❌ IfcOpenShell is required for IFC export")
        return False
    
    logging.info("Creating IFC 4x3 from CSV: %s", csv_file)
    
    # Read survey points - handle different CSV formats
    points = []
    with open(csv_file, 'r', newline='', encoding='utf-8') as f:
        # Detect delimiter by checking first line
        first_line = f.readline()
        f.seek(0)
        delimiter = ';' if ';' in first_line else ','
        
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            # Handle different column name formats
            code_col = 'Code' if 'Code' in row else 'code'
            id_col = 'ID' if 'ID' in row else 'localId'
            x_col = 'X' if 'X' in row else 'x'
            y_col = 'Y' if 'Y' in row else 'y'
            z_col = 'Z' if 'Z' in row else 'z'
            desc_col = 'Description' if 'Description' in row else 'description'
            
            # Skip origin point if present
            if row.get(code_col, '') == 'ORIGIN':
                continue
                
            # Normalize row format
            normalized_row = {
                'ID': row[id_col],
                'X': row[x_col],
                'Y': row[y_col], 
                'Z': row[z_col],
                'Code': row.get(code_col, 'UNKNOWN'),
                'Description': row.get(desc_col, '')
            }
            points.append(normalized_row)
    
    if not points:
        logging.error("No survey points found in CSV")
        return False
    
    logging.info("Processing %d survey points", len(points))
    
    # Create IFC file
    model = ifcopenshell.file(schema="IFC4X3")
    
    # Create basic project structure
    project = model.create_entity("IfcProject")
    project.GlobalId = ifcopenshell.guid.new()
    project.Name = "Survey Points Project"
    project.Description = "Survey points imported from CSV"
    
    # Create units
    length_unit = model.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")
    unit_assignment = model.create_entity("IfcUnitAssignment", Units=[length_unit])
    project.UnitsInContext = unit_assignment
    
    # Create ownership history
    person = model.create_entity("IfcPerson", GivenName="Survey", FamilyName="Processor")
    organization = model.create_entity("IfcOrganization", Name="Survey Team")
    person_org = model.create_entity("IfcPersonAndOrganization", 
                                    ThePerson=person, TheOrganization=organization)
    
    application = model.create_entity("IfcApplication")
    application.ApplicationDeveloper = organization
    application.ApplicationFullName = "CSV to IFC Converter"
    application.Version = "1.0"
    
    owner_history = model.create_entity("IfcOwnerHistory")
    owner_history.OwningUser = person_org
    owner_history.OwningApplication = application
    owner_history.State = "READWRITE"
    owner_history.ChangeAction = "ADDED"
    owner_history.CreationDate = int(datetime.now().timestamp())
    
    project.OwnerHistory = owner_history

    # Create geometric representation context
    context_origin = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    world_axis = model.create_entity("IfcAxis2Placement3D", Location=context_origin)
    context = model.create_entity("IfcGeometricRepresentationContext")
    context.ContextType = "Model"
    context.CoordinateSpaceDimension = 3
    context.Precision = 0.001
    context.WorldCoordinateSystem = world_axis
    project.RepresentationContexts = [context]
    
    # Create site
    site = model.create_entity("IfcSite")
    site.GlobalId = ifcopenshell.guid.new()
    site.Name = "Survey Site"
    site.Description = "Site containing survey points"
    site.OwnerHistory = owner_history

    # Assign site placement at origin
    site_origin = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
    site_axis = model.create_entity("IfcAxis2Placement3D", Location=site_origin)
    site_placement = model.create_entity("IfcLocalPlacement", RelativePlacement=site_axis)
    site.ObjectPlacement = site_placement
    
    # Create coordinate system with georeferencing
    if transform_info and 'local_origin' in transform_info:
        origin = transform_info['local_origin']
        logging.info("Using georeferencing with origin: (%.3f, %.3f, %.3f)", origin['x'], origin['y'], origin['z'])
        
        # Create projected CRS for SWEREF99 TM
        projected_crs = model.create_entity("IfcProjectedCRS")
        projected_crs.Name = "SWEREF99 TM"
        projected_crs.Description = "Swedish national coordinate reference system"
        projected_crs.GeodeticDatum = "SWEREF99"
        projected_crs.VerticalDatum = "RH2000"
        projected_crs.MapProjection = "Transverse Mercator"
        projected_crs.MapZone = "TM"
        projected_crs.MapUnit = length_unit
        
        # Create map conversion for georeferencing
        map_conversion = model.create_entity("IfcMapConversion")
        map_conversion.SourceCRS = context
        map_conversion.TargetCRS = projected_crs
        map_conversion.Eastings = origin['x']
        map_conversion.Northings = origin['y']
        map_conversion.OrthogonalHeight = origin['z']
        map_conversion.XAxisAbscissa = 1.0
        map_conversion.XAxisOrdinate = 0.0
        map_conversion.Scale = 1.0
    
    # Create spatial structure
    rel_aggregates = model.create_entity("IfcRelAggregates")
    rel_aggregates.GlobalId = ifcopenshell.guid.new()
    rel_aggregates.RelatingObject = project
    rel_aggregates.RelatedObjects = [site]
    
    # Create survey annotations
    annotations = []
    contained_elements = []
    
    for point_data in points:
        # Get coordinates
        x = float(point_data['X'])
        y = float(point_data['Y'])
        z = float(point_data['Z'])
        point_id = point_data['ID']
        description = point_data.get('Description', '')
        code = point_data.get('Code', 'UNKNOWN')
        
        # Calculate original coordinates
        orig_x, orig_y, orig_z = x, y, z
        if transform_info and 'local_origin' in transform_info:
            origin = transform_info['local_origin']
            orig_x = x + origin['x']
            orig_y = y + origin['y']
            orig_z = z + origin['z']
        
        # Create property set with survey data
        properties = [
            model.create_entity("IfcPropertySingleValue", 
                               Name="ID", 
                               NominalValue=model.create_entity("IfcLabel", point_id)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="Description", 
                               NominalValue=model.create_entity("IfcText", description)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="Code", 
                               NominalValue=model.create_entity("IfcLabel", code)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="LocalX", 
                               NominalValue=model.create_entity("IfcReal", x)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="LocalY", 
                               NominalValue=model.create_entity("IfcReal", y)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="LocalZ", 
                               NominalValue=model.create_entity("IfcReal", z)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="OriginalX", 
                               NominalValue=model.create_entity("IfcReal", orig_x)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="OriginalY", 
                               NominalValue=model.create_entity("IfcReal", orig_y)),
            model.create_entity("IfcPropertySingleValue", 
                               Name="OriginalZ", 
                               NominalValue=model.create_entity("IfcReal", orig_z))
        ]
        
        property_set = model.create_entity("IfcPropertySet")
        property_set.GlobalId = ifcopenshell.guid.new()
        property_set.Name = "SurveyData"
        property_set.HasProperties = properties
        
        # Create geometry representation
        rep_point = model.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        shape_representation = model.create_entity(
            "IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Point",
            RepresentationType="Point",
            Items=[rep_point]
        )
        product_shape = model.create_entity("IfcProductDefinitionShape", Representations=[shape_representation])

        # Placement for annotation relative to site
        placement_point = model.create_entity("IfcCartesianPoint", Coordinates=(x, y, z))
        placement_axis = model.create_entity("IfcAxis2Placement3D", Location=placement_point)
        object_placement = model.create_entity("IfcLocalPlacement", PlacementRelTo=site_placement, RelativePlacement=placement_axis)

        # Create IfcAnnotation object for survey point
        annotation = model.create_entity("IfcAnnotation")
        annotation.GlobalId = ifcopenshell.guid.new()
        annotation.OwnerHistory = owner_history
        annotation.Name = f"Point {point_id}"
        annotation.Description = description or ""
        annotation.ObjectPlacement = object_placement
        annotation.Representation = product_shape
        annotation.PredefinedType = "SURVEY"
        
        # Create relationship to assign property set
        rel_defines = model.create_entity("IfcRelDefinesByProperties")
        rel_defines.GlobalId = ifcopenshell.guid.new()
        rel_defines.RelatingPropertyDefinition = property_set
        rel_defines.RelatedObjects = [annotation]
        
        annotations.append(annotation)
        contained_elements.append(annotation)
    
    # Create spatial containment relationship
    if contained_elements:
        rel_contains = model.create_entity("IfcRelContainedInSpatialStructure")
        rel_contains.GlobalId = ifcopenshell.guid.new()
        rel_contains.RelatingStructure = site
        rel_contains.RelatedElements = contained_elements
    
    # Write IFC file
    model.write(str(output_file))
    
    # Convert to Path object for stat() method
    output_path = Path(output_file)
    logging.info("IFC 4x3 file created: %s", output_file)
    logging.info("File size: %s bytes", output_path.stat().st_size)
    logging.info("Content: %d IfcCartesianPoint objects with SurveyData property sets", len(annotations))
    
    if transform_info:
        logging.info("Georeferencing: IfcMapConversion with SWEREF99 TM coordinate system")
    
    return True

def main():
    """Test the simple IFC export"""
    print("🚀 Simple CSV to IFC 4x3 Export")
    print("=" * 50)
    
    # File paths
    csv_file = Path("data/processed/client_survey_processed.csv")
    transform_file = Path("data/processed/client_survey_processed_transform_info.json")
    output_file = Path("data/output/client_survey_simple.ifc")
    
    if not csv_file.exists():
        print(f"❌ CSV file not found: {csv_file}")
        return False
    
    # Load transformation info
    transform_info = None
    if transform_file.exists():
        with open(transform_file, 'r') as f:
            transform_info = json.load(f)
        print(f"✅ Loaded transformation info")
    
    # Create IFC
    success = create_basic_ifc_with_survey_points(csv_file, output_file, transform_info)
    
    if success:
        print(f"\n🎉 Export completed successfully!")
        print(f"📁 IFC file: {output_file}")
        print(f"\n📚 Next steps:")
        print(f"1. Open {output_file} in Blender with Bonsai addon")
        print(f"2. Survey points appear as IfcCartesianPoint objects")
        print(f"3. Each point has SurveyData property set with metadata")
        print(f"4. Use points as snap targets for design modeling")
        print(f"5. Model roads, terraces, utilities as additional IFC elements")
    
    return success

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)