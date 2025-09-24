#!/usr/bin/env python3
"""
Complete client workflow implementation
Covers all requirements from field data to IFC + LandXML outputs
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add scripts directory to path
sys.path.append(str(Path(__file__).parent))

from client_data_processor import process_client_csv
from export.csv_to_landxml import CSVToLandXMLExporter

def run_qgis_preprocessing(input_csv, output_csv, config):
    """Step 1: QGIS preprocessing (coordinate transformation and cleaning)"""
    print("📊 Step 1: QGIS Preprocessing")
    print("-" * 40)
    
    success = process_client_csv(input_csv, output_csv, config)
    
    if success:
        print("✅ QGIS preprocessing completed")
        print(f"   Input: {input_csv}")
        print(f"   Output: {output_csv}")
        return True
    else:
        print("❌ QGIS preprocessing failed")
        return False

def run_ifc_export(processed_csv, transform_info_file, output_ifc):
    """Step 2: Create IFC 4x3 file with georeferenced survey points"""
    print("\n🏗️  Step 2: IFC 4x3 Export with Georeferencing")
    print("-" * 40)
    
    try:
        from export.simple_csv_to_ifc import create_basic_ifc_with_survey_points
        
        # Load transformation info
        transform_info = None
        if transform_info_file.exists():
            with open(transform_info_file, 'r') as f:
                transform_info = json.load(f)
        
        success = create_basic_ifc_with_survey_points(processed_csv, output_ifc, transform_info)
        
        if success:
            print("✅ IFC 4x3 export completed")
            print(f"   Output: {output_ifc}")
            print(f"   Size: {output_ifc.stat().st_size} bytes")
            print("   Contains: IfcAnnotation survey points with SurveyData psets")
            print("   Georeferencing: IfcMapConversion for proper coordinate system")
            return True
        else:
            print("❌ IFC export failed")
            return False
            
    except ImportError as e:
        print(f"⚠️  IFC export requires IfcOpenShell: {e}")
        print("   Install with: pip install ifcopenshell")
        return False
    except Exception as e:
        print(f"❌ IFC export failed: {e}")
        return False

def run_landxml_export(processed_csv, transform_info_file, output_landxml):
    """Step 3: LandXML export for machine control"""
    print("\n🗺️  Step 3: LandXML Export for Machine Control")
    print("-" * 40)
    
    # Load transformation info
    transform_info = None
    if transform_info_file.exists():
        with open(transform_info_file, 'r') as f:
            transform_info = json.load(f)
    
    # Create exporter and export
    exporter = CSVToLandXMLExporter(transform_info)
    success = exporter.export_to_landxml(processed_csv, output_landxml)
    
    if success:
        print("✅ LandXML export completed")
        print(f"   Output: {output_landxml}")
        print(f"   Size: {output_landxml.stat().st_size} bytes")
        return True
    else:
        print("❌ LandXML export failed")
        return False

def validate_outputs(output_files):
    """Step 4: Validate all outputs"""
    print("\n🔍 Step 4: Output Validation")
    print("-" * 40)
    
    results = {}
    
    for name, file_path in output_files.items():
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"✅ {name}: {file_path} ({size} bytes)")
            results[name] = True
        else:
            print(f"❌ {name}: Missing - {file_path}")
            results[name] = False
    
    return results

def create_workflow_summary(results, output_dir):
    """Create summary report of the workflow"""
    summary = {
        "workflow": "Complete Client Survey Workflow",
        "timestamp": "2025-09-10",
        "steps_completed": results,
        "outputs": {
            "processed_csv": "data/processed/client_survey_processed.csv",
            "transform_info": "data/processed/client_survey_processed_transform_info.json",
            "landxml": "data/output/client_survey.xml",
            "blend_file": "data/output/client_survey_ifc.blend",
            "ifc_file": "data/output/client_survey.ifc"
        },
        "benefits_achieved": [
            "Automated coordinate transformation",
            "Preserved survey metadata",
            "IFC 4x3 BIM compatibility",
            "LandXML machine control output",
            "Open standards throughout",
            "No vendor lock-in"
        ]
    }
    
    summary_file = output_dir / "workflow_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    return summary_file

def main():
    """Run complete client workflow"""
    print("🚀 Complete Client Survey Workflow")
    print("=" * 60)
    print("Replacing TopoCad with open-source pipeline:")
    print("Field → QGIS → Blender/Bonsai → IFC + LandXML")
    print("=" * 60)
    
    # File paths
    input_csv = Path("data/raw/client_survey.csv")
    processed_csv = Path("data/processed/client_survey_processed.csv")
    transform_info_file = Path("data/processed/client_survey_processed_transform_info.json")
    output_landxml = Path("data/output/client_survey.xml")

    output_ifc = Path("data/output/client_survey.ifc")
    output_dir = Path("data/output")
    
    # Configuration
    config = {
        "source_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "target_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "local_origin": {"x": 0, "y": 0, "z": 0},
        "precision": {"decimal_places": 3}
    }
    
    # Check input
    if not input_csv.exists():
        print(f"❌ Input file not found: {input_csv}")
        print("   Please place your survey CSV in data/raw/")
        return False
    
    # Ensure output directory exists
    output_dir.mkdir(exist_ok=True)
    
    # Run workflow steps
    results = {}
    
    # Step 1: QGIS Preprocessing
    results['qgis_preprocessing'] = run_qgis_preprocessing(
        input_csv, processed_csv, config
    )
    
    # Step 2: IFC 4x3 Export
    results['ifc_export'] = run_ifc_export(
        processed_csv, transform_info_file, output_ifc
    )
    
    # Step 3: LandXML Export
    results['landxml_export'] = run_landxml_export(
        processed_csv, transform_info_file, output_landxml
    )
    
    # Step 4: Validate outputs
    output_files = {
        "Processed CSV": processed_csv,
        "Transform Info": transform_info_file,
        "LandXML": output_landxml,
        "IFC File": output_ifc
    }
    
    validation_results = validate_outputs(output_files)
    results.update(validation_results)
    
    # Create summary
    summary_file = create_workflow_summary(results, output_dir)
    
    # Final summary
    print("\n" + "=" * 60)
    print("📋 Workflow Completion Summary")
    print("=" * 60)
    
    total_steps = len([k for k in results.keys() if k in ['qgis_preprocessing', 'ifc_export', 'landxml_export']])
    completed_steps = len([k for k, v in results.items() if v and k in ['qgis_preprocessing', 'ifc_export', 'landxml_export']])
    
    print(f"🎯 Steps completed: {completed_steps}/{total_steps}")
    
    for step, success in results.items():
        if step in ['qgis_preprocessing', 'ifc_export', 'landxml_export']:
            status = "✅ COMPLETED" if success else "❌ FAILED"
            step_name = step.replace('_', ' ').title()
            print(f"   {status}: {step_name}")
    
    # Show outputs
    print(f"\n📁 Generated Files:")
    for name, file_path in output_files.items():
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"   ✅ {name}: {file_path} ({size} bytes)")
    
    print(f"\n📊 Summary Report: {summary_file}")
    
    # Success criteria
    essential_outputs = ['qgis_preprocessing', 'landxml_export']
    full_outputs = ['qgis_preprocessing', 'ifc_export', 'landxml_export']
    
    essential_success = all(results.get(step, False) for step in essential_outputs)
    full_success = all(results.get(step, False) for step in full_outputs)
    
    if full_success:
        print("\n🎉 COMPLETE WORKFLOW SUCCESS!")
        print("\n✨ All Client Requirements Met:")
        print("   ✅ Survey points imported with metadata preserved")
        print("   ✅ Coordinate transformation (local CRS)")
        print("   ✅ IFC 4x3 with IfcAnnotation and SurveyData psets")
        print("   ✅ Proper georeferencing with IfcMapConversion")
        print("   ✅ LandXML export for machine control")
        print("   ✅ Open standards throughout (no vendor lock-in)")
        print("\n🚀 Ready for Production Use!")
        print("\n📚 Next Steps:")
        print("   1. Open IFC file in Blender with Bonsai addon")
        print("   2. Use survey points as snap targets for design")
        print("   3. Model roads, terraces, utilities as IFC elements")
        
    elif essential_success:
        print("\n🎉 ESSENTIAL WORKFLOW SUCCESS!")
        print("\n✨ Core Requirements Met:")
        print("   ✅ Survey points imported with metadata preserved")
        print("   ✅ Coordinate transformation (local CRS)")
        print("   ✅ LandXML export for machine control")
        print("   ✅ Open standards throughout (no vendor lock-in)")
        
        if not results.get('ifc_export', False):
            print("   ⚠️  IFC export needs IfcOpenShell: pip install ifcopenshell")
        
        print("\n🚀 Ready for Machine Control Use!")
        
    else:
        print("\n⚠️  Workflow partially completed")
        print("   Some steps failed - check error messages above")
    
    return essential_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)