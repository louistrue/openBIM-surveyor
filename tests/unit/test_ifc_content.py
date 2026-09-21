"""
Inspect the IFC file to see what entities we actually created
"""

try:
    import ifcopenshell
except ImportError:
    ifcopenshell = None
from pathlib import Path

def inspect_ifc_file(ifc_path):
    """Inspect the contents of the IFC file"""
    print(f"🔍 Inspecting IFC file: {ifc_path}")

    if ifcopenshell is None:
        print("❌ IfcOpenShell is required to inspect IFC files")
        return False
    
    if not Path(ifc_path).exists():
        print(f"❌ File not found: {ifc_path}")
        return False
    
    try:
        model = ifcopenshell.open(ifc_path)
        print(f"✅ Opened IFC file (schema: {model.schema})")
        
        # Count entities
        entity_counts = {}
        for entity in model:
            entity_type = entity.is_a()
            entity_counts[entity_type] = entity_counts.get(entity_type, 0) + 1
        
        print(f"\n📊 Entity Summary:")
        for entity_type, count in sorted(entity_counts.items()):
            print(f"   {entity_type}: {count}")
        
        # Look specifically for survey points
        survey_points = model.by_type("IfcCartesianPoint")
        print(f"\n📍 Survey Points ({len(survey_points)} IfcCartesianPoint):")
        
        for i, point in enumerate(survey_points[:5]):  # Show first 5
            print(f"   {i+1}. IfcCartesianPoint #{point.id()}")
            if hasattr(point, 'Coordinates') and point.Coordinates:
                coords = point.Coordinates
                print(f"      Coordinates: ({coords[0]:.3f}, {coords[1]:.3f}, {coords[2]:.3f})")
            print()
        
        if len(survey_points) > 5:
            print(f"   ... and {len(survey_points) - 5} more")
        
        # Check property sets
        property_sets = model.by_type("IfcPropertySet")
        survey_psets = [ps for ps in property_sets if ps.Name == "SurveyData"]
        print(f"\n📋 SurveyData Property Sets: {len(survey_psets)}")
        
        if survey_psets:
            pset = survey_psets[0]
            print(f"   Properties in first set:")
            for prop in pset.HasProperties:
                if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                    value = prop.NominalValue.wrappedValue if prop.NominalValue else "None"
                    print(f"     {prop.Name}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error inspecting IFC file: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main inspection function"""
    ifc_file = "data/output/client_survey.ifc"
    success = inspect_ifc_file(ifc_file)
    
    if success:
        print("\n✅ IFC inspection completed successfully!")
    else:
        print("\n❌ IFC inspection failed")
    
    return success

if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
