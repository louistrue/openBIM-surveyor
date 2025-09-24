"""
Export surfaces from IFC to LandXML format for machine control
Compatible with excavator systems that expect LandXML 1.2
"""

import logging
import xml.etree.ElementTree as ET
from xml.dom import minidom
import ifcopenshell
import numpy as np
from pathlib import Path

class LandXMLExporter:
    def __init__(self, config):
        self.config = config
        self.coordinate_system = config.get('target_crs', {})
        
    def create_landxml_root(self):
        """Create the root LandXML element with proper namespaces"""
        root = ET.Element("LandXML")
        root.set("xmlns", "http://www.landxml.org/schema/LandXML-1.2")
        root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
        root.set("xsi:schemaLocation", "http://www.landxml.org/schema/LandXML-1.2 http://www.landxml.org/schema/LandXML-1.2/LandXML-1.2.xsd")
        root.set("version", "1.2")
        root.set("date", "2025-09-10")  # Current date
        root.set("time", "12:00:00")
        
        return root
    
    def add_coordinate_system(self, root):
        """Add coordinate system information"""
        coord_sys = ET.SubElement(root, "CoordinateSystem")
        coord_sys.set("epsgCode", str(self.coordinate_system.get('epsg', 3857)))
        coord_sys.set("name", self.coordinate_system.get('name', 'Local'))
        
        return coord_sys
    
    def add_project_info(self, root, project_name="Survey Project"):
        """Add project metadata"""
        project = ET.SubElement(root, "Project")
        project.set("name", project_name)
        
        application = ET.SubElement(project, "Application")
        application.set("name", "Open BIM Survey Workflow")
        application.set("version", "1.0")
        
        return project
    
    def extract_surface_from_ifc(self, ifc_file):
        """Extract triangulated surface data from IFC file"""
        try:
            logging.info("Opening IFC file for LandXML export: %s", ifc_file)
            model = ifcopenshell.open(ifc_file)
            surfaces = []
            points = []
            
            # Look for IfcGeographicElement (terrain) first
            try:
                geographic_elements = model.by_type("IfcGeographicElement")
                for element in geographic_elements:
                    if hasattr(element, 'Representation') and element.Representation:
                        surface_data = self.extract_mesh_data(element)
                        if surface_data:
                            surfaces.append({
                                'name': element.Name or f"Surface_{element.id()}",
                                'vertices': surface_data['vertices'],
                                'faces': surface_data['faces']
                            })
                logging.info("Found %d IfcGeographicElement surfaces", len(surfaces))
            except:
                logging.info("No IfcGeographicElement found or accessible")
            
            # Look for other surface-like elements if no geographic elements found
            if not surfaces:
                surface_types = [
                    "IfcSlab", "IfcRoof", "IfcWall", "IfcBeam", "IfcColumn", 
                    "IfcMember", "IfcPlate", "IfcCurtainWall", "IfcRamp",
                    "IfcStair", "IfcFooting", "IfcPile", "IfcCovering"
                ]
                
                for ifc_type in surface_types:
                    try:
                        elements = model.by_type(ifc_type)
                        for element in elements:
                            if hasattr(element, 'Representation') and element.Representation:
                                surface_data = self.extract_mesh_data(element)
                                if surface_data:
                                    surfaces.append({
                                        'name': element.Name or f"{ifc_type}_{element.id()}",
                                        'vertices': surface_data['vertices'],
                                        'faces': surface_data['faces']
                                    })
                        if elements:
                            logging.info("Found %d %s elements", len(elements), ifc_type)
                    except:
                        continue
            
            # Look for survey points in IfcAnnotation objects
            try:
                annotations = model.by_type("IfcAnnotation")
                for annotation in annotations:
                    point_data = self.extract_point_data(annotation)
                    if point_data:
                        points.append(point_data)
                if points:
                    logging.info("Found %d IfcAnnotation survey points", len(points))
            except:
                logging.info("No IfcAnnotation objects found or accessible")
            
            # Look for IfcCartesianPoint objects (direct point data)
            try:
                cartesian_points = model.by_type("IfcCartesianPoint")
                for cp in cartesian_points:
                    if hasattr(cp, 'Coordinates') and cp.Coordinates:
                        coords = cp.Coordinates
                        if len(coords) >= 3:
                            points.append({
                                'id': f"Point_{cp.id()}",
                                'x': float(coords[0]),
                                'y': float(coords[1]),
                                'z': float(coords[2]),
                                'code': 'POINT',
                                'description': f'CartesianPoint_{cp.id()}'
                            })
                if len(cartesian_points) > len(points):  # Only log if we found additional points
                    logging.info("Found %d IfcCartesianPoint objects", len(cartesian_points))
            except:
                logging.info("No IfcCartesianPoint objects found or accessible")
            
            # If we have points but no surfaces, create a triangulated surface from points
            if points and not surfaces:
                logging.info("Creating triangulated surface from %d survey points", len(points))
                surface_from_points = self.create_surface_from_points(points)
                if surface_from_points:
                    surfaces.append(surface_from_points)
            
            # Store points for CgPoints export
            self.survey_points = points
            
            return surfaces
            
        except Exception as e:
            logging.exception("Error reading IFC file: %s", e)
            return []
    
    def extract_mesh_data(self, ifc_element):
        """Extract mesh vertices and faces from IFC element"""
        try:
            # This is a simplified extraction - real implementation would need
            # to handle IFC geometry representation properly
            if not hasattr(ifc_element, 'Representation'):
                return None
                
            # Get the shape representation
            shape = ifcopenshell.geom.create_shape(
                ifcopenshell.geom.settings(), ifc_element
            )
            
            if shape:
                # Get vertices and faces
                vertices = shape.geometry.verts
                faces = shape.geometry.faces
                
                # Reshape vertices (they come as flat array)
                vertices = np.array(vertices).reshape(-1, 3)
                faces = np.array(faces).reshape(-1, 3)
                
                return {
                    'vertices': vertices,
                    'faces': faces
                }
                
        except Exception as e:
            logging.exception("Error extracting mesh data: %s", e)
            
        return None
    
    def extract_point_data(self, ifc_annotation):
        """Extract survey point data from IfcAnnotation objects"""
        try:
            # Get the placement/position
            x, y, z = 0.0, 0.0, 0.0
            
            if hasattr(ifc_annotation, 'ObjectPlacement') and ifc_annotation.ObjectPlacement:
                placement = ifc_annotation.ObjectPlacement
                if hasattr(placement, 'RelativePlacement') and placement.RelativePlacement:
                    rel_placement = placement.RelativePlacement
                    if hasattr(rel_placement, 'Location') and rel_placement.Location:
                        location = rel_placement.Location
                        if hasattr(location, 'Coordinates') and location.Coordinates:
                            coords = location.Coordinates
                            x = float(coords[0]) if len(coords) > 0 else 0.0
                            y = float(coords[1]) if len(coords) > 1 else 0.0
                            z = float(coords[2]) if len(coords) > 2 else 0.0
            
            # Extract properties from property sets
            point_id = f"Point_{ifc_annotation.id()}"
            code = "SURVEY"
            description = ifc_annotation.Description or ""
            
            # Look for SurveyData property set
            if hasattr(ifc_annotation, 'IsDefinedBy') and ifc_annotation.IsDefinedBy:
                for rel in ifc_annotation.IsDefinedBy:
                    if hasattr(rel, 'RelatingPropertyDefinition'):
                        prop_def = rel.RelatingPropertyDefinition
                        if hasattr(prop_def, 'Name') and prop_def.Name == "SurveyData":
                            if hasattr(prop_def, 'HasProperties'):
                                for prop in prop_def.HasProperties:
                                    if hasattr(prop, 'Name') and hasattr(prop, 'NominalValue'):
                                        prop_name = prop.Name
                                        if hasattr(prop.NominalValue, 'wrappedValue'):
                                            prop_value = prop.NominalValue.wrappedValue
                                        else:
                                            prop_value = str(prop.NominalValue)
                                        
                                        if prop_name == "ID":
                                            point_id = str(prop_value)
                                        elif prop_name == "Code":
                                            code = str(prop_value)
                                        elif prop_name == "Description":
                                            description = str(prop_value)
                                        elif prop_name == "OriginalX":
                                            x = float(prop_value)
                                        elif prop_name == "OriginalY":
                                            y = float(prop_value)
                                        elif prop_name == "OriginalZ":
                                            z = float(prop_value)
            
            return {
                'id': point_id,
                'x': x,
                'y': y,
                'z': z,
                'code': code,
                'description': description
            }
            
        except Exception as e:
            logging.exception("Error extracting point data from annotation %s: %s", ifc_annotation.id(), e)
            return None
    
    def create_surface_from_points(self, points):
        """Create a triangulated surface from survey points"""
        try:
            if len(points) < 3:
                logging.warning("Need at least 3 points for triangulation, got %d", len(points))
                return None
            
            import numpy as np
            from scipy.spatial import Delaunay
            
            # Extract 2D coordinates for triangulation
            coords_2d = np.array([[p['x'], p['y']] for p in points])
            coords_3d = np.array([[p['x'], p['y'], p['z']] for p in points])
            
            # Create Delaunay triangulation
            tri = Delaunay(coords_2d)
            
            logging.info("Created triangulation with %d triangles from %d points", len(tri.simplices), len(points))
            
            return {
                'name': "Survey_Points_Surface",
                'vertices': coords_3d,
                'faces': tri.simplices
            }
            
        except ImportError:
            logging.error("SciPy not available for triangulation")
            return None
        except Exception as e:
            logging.exception("Error creating surface from points: %s", e)
            return None
    
    def create_surface_xml(self, surface_data, parent):
        """Create LandXML Surface element"""
        surface = ET.SubElement(parent, "Surface")
        surface.set("name", surface_data['name'])
        
        # Definition
        definition = ET.SubElement(surface, "Definition")
        definition.set("surfType", "TIN")
        
        # Points (Pnts)
        pnts = ET.SubElement(definition, "Pnts")
        vertices = surface_data['vertices']
        
        for i, vertex in enumerate(vertices):
            pnt = ET.SubElement(pnts, "P")
            pnt.set("id", str(i + 1))
            pnt.text = f"{vertex[0]:.3f} {vertex[1]:.3f} {vertex[2]:.3f}"
        
        # Faces
        faces_elem = ET.SubElement(definition, "Faces")
        faces = surface_data['faces']
        
        for i, face in enumerate(faces):
            face_elem = ET.SubElement(faces_elem, "F")
            # LandXML faces are 1-indexed
            face_elem.text = f"{face[0]+1} {face[1]+1} {face[2]+1}"
        
        return surface
    
    def export_to_landxml(self, ifc_file, output_file):
        """Main export function"""
        logging.info("Exporting IFC to LandXML: %s -> %s", ifc_file, output_file)
        
        # Extract surfaces from IFC
        surfaces = self.extract_surface_from_ifc(ifc_file)
        survey_points = getattr(self, 'survey_points', [])
        
        if not surfaces and not survey_points:
            logging.warning("No surfaces or survey points found in IFC file")
            return False
        
        # Create LandXML structure
        root = self.create_landxml_root()
        self.add_coordinate_system(root)
        self.add_project_info(root)
        
        # Add survey points as CgPoints if found
        if survey_points:
            cg_points = ET.SubElement(root, "CgPoints")
            cg_points.set("name", "Survey Points")
            cg_points.set("desc", f"Survey points extracted from IFC ({len(survey_points)} points)")
            
            for point in survey_points:
                cg_point = ET.SubElement(cg_points, "CgPoint")
                cg_point.set("name", str(point['id']))
                cg_point.set("code", point['code'])
                cg_point.set("desc", point['description'])
                cg_point.text = f"{point['x']:.3f} {point['y']:.3f} {point['z']:.3f}"
            
            logging.info("Added %d survey points as CgPoints", len(survey_points))
        
        # Add surfaces if found
        if surfaces:
            surfaces_elem = ET.SubElement(root, "Surfaces")
            
            for surface_data in surfaces:
                self.create_surface_xml(surface_data, surfaces_elem)
                logging.info("Added surface: %s", surface_data['name'])
        
        # Write to file with pretty formatting
        rough_string = ET.tostring(root, 'unicode')
        reparsed = minidom.parseString(rough_string)
        pretty_xml = reparsed.toprettyxml(indent="  ")
        
        # Remove empty lines
        pretty_xml = '\n'.join([line for line in pretty_xml.split('\n') if line.strip()])
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(pretty_xml)
        
        logging.info("LandXML exported successfully: %s", output_file)
        logging.info("Export summary: %d surfaces, %d survey points", len(surfaces), len(survey_points))
        return True

def export_to_landxml(ifc_file, landxml_output, config):
    """Convenience function for the main workflow"""
    exporter = LandXMLExporter(config)
    return exporter.export_to_landxml(ifc_file, landxml_output)

if __name__ == "__main__":
    # Example usage
    import sys
    if len(sys.argv) >= 3:
        ifc_file = sys.argv[1]
        output_file = sys.argv[2]
        config = {"target_crs": {"epsg": 3857, "name": "Web Mercator"}}
        
        exporter = LandXMLExporter(config)
        exporter.export_to_landxml(ifc_file, output_file)