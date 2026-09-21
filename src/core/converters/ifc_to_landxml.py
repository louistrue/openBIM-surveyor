"""Produce LandXML 1.2 TINs from an explicitly selected IFC terrain.

The producer intentionally has a narrow contract. A caller must select one
``IfcGeographicElement`` by GlobalId and that element must contain an authored
``IfcTriangulatedFaceSet``. It does not turn arbitrary model geometry or
``IfcCartesianPoint`` instances into a survey surface, and it never creates a
new triangulation. This makes the exported topology auditable.

Coordinates in the generated LandXML are always ``Northing Easting Elevation``
(N/E/Z). IFC placement, project units, map conversion and map units are
applied exactly once before that ordering is rendered.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import math
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
import xml.etree.ElementTree as ET


LANDXML_NAMESPACE = "http://www.landxml.org/schema/LandXML-1.2"
XML_SCHEMA_INSTANCE_NAMESPACE = "http://www.w3.org/2001/XMLSchema-instance"
MAX_IFC_REFERENCE_DEPTH = 128
ET.register_namespace("", LANDXML_NAMESPACE)
ET.register_namespace("xsi", XML_SCHEMA_INSTANCE_NAMESPACE)


class LandXmlExportError(ValueError):
    """Raised when IFC cannot meet the producer's explicit export contract."""


@dataclass(frozen=True)
class TerrainSelection:
    """The sole terrain to export, identified by its IFC GlobalId."""

    global_id: str


@dataclass(frozen=True)
class TerrainMesh:
    """Authored triangulation in map metres, before LandXML N/E/Z rendering."""

    name: str
    vertices_enz: tuple[tuple[float, float, float], ...]
    faces: tuple[tuple[int, int, int], ...]
    crs_name: str


def export_ifc_terrain_to_landxml(
    ifc_path: str | Path,
    output_path: str | Path,
    *,
    terrain_global_id: str,
    project_name: str | None = None,
) -> TerrainMesh:
    """Open an IFC and atomically write one standards-shaped LandXML 1.2 TIN.

    ``terrain_global_id`` is deliberately mandatory. Selecting a terrain by
    name, type-wide scan, or coordinate heuristics would make an export depend
    on unrelated building geometry.
    """

    if not terrain_global_id:
        raise LandXmlExportError(
            "Terrain selection is required: provide the terrain IfcGeographicElement GlobalId."
        )
    source = Path(ifc_path)
    if not source.is_file():
        raise LandXmlExportError(f"IFC input does not exist or is not a file: {source}")
    _reject_input_output_overlap(source, Path(output_path))
    try:
        import ifcopenshell
    except ImportError as exc:  # pragma: no cover - depends on deployment
        raise LandXmlExportError(
            "IfcOpenShell is required to read IFC files. Install the 'ifcopenshell' package."
        ) from exc
    try:
        model = ifcopenshell.open(str(source))
    except Exception as exc:  # pragma: no cover - depends on corrupt user input
        raise LandXmlExportError(f"Could not open IFC '{source}': {exc}") from exc

    mesh = produce_terrain_mesh(model, TerrainSelection(terrain_global_id))
    document = build_landxml_document(mesh, project_name=project_name or source.stem)
    write_validated_landxml(output_path, document)
    return mesh


def produce_terrain_mesh(model: Any, selection: TerrainSelection) -> TerrainMesh:
    """Extract a selected terrain's authored TIN from an already-open IFC model."""

    terrain = _get_terrain_by_global_id(model, selection.global_id)
    representations = _representations(terrain)
    face_sets = [
        item
        for representation in representations
        for item in _items(representation)
        if _is_a(item, "IfcTriangulatedFaceSet")
    ]
    if not face_sets:
        raise LandXmlExportError(
            f"Selected terrain '{selection.global_id}' has no IfcTriangulatedFaceSet. "
            "Export an authored triangulated terrain from Bonsai; this producer does not "
            "triangulate points or building geometry."
        )
    if len(face_sets) != 1:
        raise LandXmlExportError(
            f"Selected terrain '{selection.global_id}' has {len(face_sets)} triangulated face sets. "
            "Select or author one terrain TIN per IFC product before exporting."
        )

    face_set = face_sets[0]
    if _is_a(face_set, "IfcTriangulatedIrregularNetwork"):
        raise LandXmlExportError(
            "IfcTriangulatedIrregularNetwork is not supported because its Flags can mark "
            "faces invisible or define voids. Export an IfcTriangulatedFaceSet without Flags "
            "or use a flag-preserving exporter; this producer will not publish hidden faces."
        )
    vertices = _vertices_by_pn_index(face_set, _coord_list(face_set))
    faces = _coord_index(face_set, len(vertices))
    representation = next(
        representation
        for representation in representations
        if face_set in _items(representation)
    )
    conversion, map_context = _map_conversion_for_context(
        model, getattr(representation, "ContextOfItems", None)
    )
    _reject_nonidentity_world_coordinate_system(map_context)
    source_to_metre = _project_length_to_metre(model)
    map_to_metre = _unit_to_metre(getattr(getattr(conversion, "TargetCRS", None), "MapUnit", None))
    _require_explicit_scale_for_unit_change(conversion, source_to_metre, map_to_metre)
    placement = _placement_matrix(getattr(terrain, "ObjectPlacement", None))

    transformed = tuple(
        _map_coordinate(
            _transform_point(placement, vertex),
            conversion,
            map_to_metre=map_to_metre,
        )
        for vertex in vertices
    )
    crs_name = _required_text(getattr(getattr(conversion, "TargetCRS", None), "Name", None), "TargetCRS.Name")
    mesh = TerrainMesh(
        name=_terrain_name(terrain, selection.global_id),
        vertices_enz=transformed,
        faces=faces,
        crs_name=crs_name,
    )
    _validate_mesh(mesh)
    return mesh


def build_landxml_document(mesh: TerrainMesh, *, project_name: str) -> bytes:
    """Build a LandXML 1.2 document using metre units and N/E/Z coordinates."""

    _validate_mesh(mesh)
    now = datetime.now(timezone.utc)
    root = ET.Element(
        _tag("LandXML"),
        {
            "version": "1.2",
            "date": now.date().isoformat(),
            "time": now.strftime("%H:%M:%S"),
            f"{{{XML_SCHEMA_INSTANCE_NAMESPACE}}}schemaLocation": (
                f"{LANDXML_NAMESPACE} {LANDXML_NAMESPACE}/LandXML-1.2.xsd"
            ),
        },
    )
    units = ET.SubElement(root, _tag("Units"))
    ET.SubElement(
        units,
        _tag("Metric"),
        {
            "linearUnit": "meter",
            "areaUnit": "squareMeter",
            "volumeUnit": "cubicMeter",
            "temperatureUnit": "celsius",
            "pressureUnit": "HPA",
            "angularUnit": "decimal degrees",
            "directionUnit": "decimal degrees",
            "elevationUnit": "meter",
        },
    )
    ET.SubElement(root, _tag("CoordinateSystem"), {"name": mesh.crs_name})
    ET.SubElement(root, _tag("Project"), {"name": project_name})
    ET.SubElement(
        root,
        _tag("Application"),
        {"name": "bonsai-topo", "version": "1.0.0", "manufacturer": "bonsai-topo"},
    )
    surfaces = ET.SubElement(root, _tag("Surfaces"))
    surface = ET.SubElement(surfaces, _tag("Surface"), {"name": mesh.name, "desc": mesh.crs_name})
    definition = ET.SubElement(surface, _tag("Definition"), {"surfType": "TIN"})
    points = ET.SubElement(definition, _tag("Pnts"))
    for index, (easting, northing, elevation) in enumerate(mesh.vertices_enz, start=1):
        # LandXML coordinates are Northing, Easting, Elevation, not IFC X/Y/Z.
        point = ET.SubElement(points, _tag("P"), {"id": str(index)})
        point.text = _format_coordinate(northing, easting, elevation)
    faces = ET.SubElement(definition, _tag("Faces"))
    for face in mesh.faces:
        element = ET.SubElement(faces, _tag("F"))
        element.text = " ".join(str(index) for index in face)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_validated_landxml(output_path: str | Path, document: bytes) -> None:
    """Validate the exact bytes to be persisted, then replace the output atomically."""

    validate_landxml_bytes(document)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(document)
        _replace_with_retry(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_with_retry(temporary: Path, destination: Path) -> None:
    """Handle Windows' transient sharing violation between concurrent writers.

    Every writer uses a unique temporary file, and the final replacement stays
    atomic. NTFS can nevertheless reject one of two simultaneous replacements
    while the other handle is closing, so retry that narrow, recoverable error
    for a short bounded interval rather than leaving a valid export unwritten.
    """

    for attempt in range(5):
        try:
            os.replace(temporary, destination)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.01 * (attempt + 1))


def validate_landxml_bytes(document: bytes) -> None:
    """Reject malformed or internally inconsistent generated LandXML bytes.

    The checks mirror the constrained LandXML 1.2 subset emitted above. They
    validate serialized bytes so a failed serializer or write path cannot
    silently produce an invalid deliverable.
    """

    try:
        root = ET.fromstring(document)
    except ET.ParseError as exc:
        raise LandXmlExportError(f"Generated LandXML is not well-formed XML: {exc}") from exc
    if root.tag != _tag("LandXML") or root.get("version") != "1.2":
        raise LandXmlExportError("Generated document is not a LandXML 1.2 root element.")
    metric = root.find(f"{_tag('Units')}/{_tag('Metric')}")
    required_metric_units = {
        "linearUnit": "meter",
        "areaUnit": "squareMeter",
        "volumeUnit": "cubicMeter",
        "temperatureUnit": "celsius",
        "pressureUnit": "HPA",
        "elevationUnit": "meter",
    }
    if metric is None or any(metric.get(name) != value for name, value in required_metric_units.items()):
        raise LandXmlExportError("Generated LandXML must declare metric metre Units.")
    if metric.get("directionUnit") not in {"radians", "grads", "decimal degrees", "decimal dd.mm.ss"}:
        raise LandXmlExportError("Generated LandXML has an invalid Metric directionUnit.")
    coordinate_system = root.find(_tag("CoordinateSystem"))
    if coordinate_system is None or not coordinate_system.get("name"):
        raise LandXmlExportError("Generated LandXML must preserve the explicit IFC target CRS name.")
    surfaces = root.findall(f"{_tag('Surfaces')}/{_tag('Surface')}")
    if len(surfaces) != 1:
        raise LandXmlExportError("Generated LandXML must contain exactly one explicitly selected surface.")
    points = surfaces[0].findall(f"{_tag('Definition')}/{_tag('Pnts')}/{_tag('P')}")
    if len(points) < 3:
        raise LandXmlExportError("Generated LandXML TIN must contain at least three points.")
    identifiers = {point.get("id") for point in points}
    if None in identifiers or len(identifiers) != len(points):
        raise LandXmlExportError("Generated LandXML TIN has missing or duplicate point identifiers.")
    coordinates_by_id = {}
    for point in points:
        values = (point.text or "").split()
        if len(values) != 3 or not all(_is_finite_number(value) for value in values):
            raise LandXmlExportError("Generated LandXML point is not a finite N/E/Z coordinate triple.")
        coordinates_by_id[point.get("id")] = tuple(float(value) for value in values)
    faces = surfaces[0].findall(f"{_tag('Definition')}/{_tag('Faces')}/{_tag('F')}")
    if not faces:
        raise LandXmlExportError("Generated LandXML TIN has no authored faces.")
    for face in faces:
        references = (face.text or "").split()
        if len(references) != 3 or any(reference not in identifiers for reference in references):
            raise LandXmlExportError("Generated LandXML face does not reference three defined TIN points.")
        _validate_triangle(
            tuple(coordinates_by_id[reference] for reference in references),
            "Generated LandXML face",
        )


def _get_terrain_by_global_id(model: Any, global_id: str) -> Any:
    try:
        terrain = getattr(model, "by_guid", lambda _: None)(global_id)
    except RuntimeError as exc:
        raise LandXmlExportError(
            f"Could not resolve terrain GlobalId '{global_id}' in the IFC: {exc}. "
            "Verify the selected IfcGeographicElement GlobalId and export the IFC again if it is stale."
        ) from exc
    if terrain is None:
        raise LandXmlExportError(
            f"No IFC entity has terrain GlobalId '{global_id}'. Use the GlobalId of the intended "
            "IfcGeographicElement, not its STEP id or display name."
        )
    if not _is_a(terrain, "IfcGeographicElement"):
        actual_type = _entity_type(terrain)
        raise LandXmlExportError(
            f"Selected GlobalId '{global_id}' is {actual_type}, not IfcGeographicElement. "
            "Building elements and annotations are intentionally not exportable as terrain."
        )
    return terrain


def _representations(terrain: Any) -> tuple[Any, ...]:
    representation = getattr(terrain, "Representation", None)
    representations = tuple(getattr(representation, "Representations", ()) or ())
    if not representations:
        raise LandXmlExportError("Selected terrain has no product shape representation.")
    return representations


def _items(representation: Any) -> tuple[Any, ...]:
    return tuple(getattr(representation, "Items", ()) or ())


def _coord_list(face_set: Any) -> tuple[tuple[float, float, float], ...]:
    coordinates = getattr(getattr(face_set, "Coordinates", None), "CoordList", None)
    if not coordinates or len(coordinates) < 3:
        raise LandXmlExportError("IfcTriangulatedFaceSet has fewer than three coordinates.")
    result = []
    for index, coordinate in enumerate(coordinates, start=1):
        if len(coordinate) != 3:
            raise LandXmlExportError(f"TIN coordinate {index} is not a three-dimensional IFC coordinate.")
        numeric = tuple(float(value) for value in coordinate)
        if not all(math.isfinite(value) for value in numeric):
            raise LandXmlExportError(f"TIN coordinate {index} contains a non-finite value.")
        result.append(numeric)
    return tuple(result)


def _coord_index(face_set: Any, vertex_count: int) -> tuple[tuple[int, int, int], ...]:
    coord_index = getattr(face_set, "CoordIndex", None)
    if not coord_index:
        raise LandXmlExportError("IfcTriangulatedFaceSet has no CoordIndex topology.")
    result = []
    for face_number, face in enumerate(coord_index, start=1):
        if len(face) != 3:
            raise LandXmlExportError(f"TIN face {face_number} is not triangular.")
        indices = tuple(int(index) for index in face)
        if len(set(indices)) != 3 or any(index < 1 or index > vertex_count for index in indices):
            raise LandXmlExportError(f"TIN face {face_number} has invalid CoordIndex references.")
        result.append(indices)
    return tuple(result)


def _vertices_by_pn_index(
    face_set: Any, coordinates: tuple[tuple[float, float, float], ...]
) -> tuple[tuple[float, float, float], ...]:
    pn_index = getattr(face_set, "PnIndex", None)
    if pn_index is None:
        return coordinates
    if not pn_index:
        raise LandXmlExportError("IfcTriangulatedFaceSet.PnIndex is empty.")
    indices = tuple(int(index) for index in pn_index)
    if any(index < 1 or index > len(coordinates) for index in indices):
        raise LandXmlExportError("IfcTriangulatedFaceSet.PnIndex references an undefined coordinate.")
    return tuple(coordinates[index - 1] for index in indices)


def _map_conversion_for_context(model: Any, context: Any) -> tuple[Any, Any]:
    if context is None:
        raise LandXmlExportError("Selected terrain representation has no geometric context for map conversion.")
    operations = tuple(getattr(model, "by_type", lambda _: ())("IfcMapConversion") or ())
    matching = []
    current_context = context
    visited_contexts = set()
    while current_context is not None:
        marker = _entity_marker(current_context)
        if marker in visited_contexts:
            raise LandXmlExportError("Geometric representation context ParentContext chain contains a cycle.")
        visited_contexts.add(marker)
        matching.extend(
            (operation, current_context)
            for operation in operations
            if _same_entity(getattr(operation, "SourceCRS", None), current_context)
        )
        current_context = getattr(current_context, "ParentContext", None)
    if not matching:
        raise LandXmlExportError(
            "Selected terrain context has no IfcMapConversion. A projected CRS and map conversion are "
            "required; the exporter will not guess a CRS or assume local coordinates are map coordinates."
        )
    if len(matching) != 1:
        raise LandXmlExportError(
            f"Selected terrain context has {len(matching)} IfcMapConversion operations; export is ambiguous."
        )
    conversion, source_context = matching[0]
    target_crs = getattr(conversion, "TargetCRS", None)
    _required_text(getattr(target_crs, "Name", None), "IfcMapConversion.TargetCRS.Name")
    if getattr(target_crs, "MapUnit", None) is None:
        raise LandXmlExportError(
            "IfcMapConversion.TargetCRS.MapUnit is required. The exporter will not guess map units."
        )
    for attribute in ("Eastings", "Northings", "OrthogonalHeight"):
        _finite_attribute(conversion, attribute)
    for attribute in ("XAxisAbscissa", "XAxisOrdinate", "Scale", "FactorX", "FactorY", "FactorZ"):
        value = getattr(conversion, attribute, None)
        if value is not None and not _is_finite_number(value):
            raise LandXmlExportError(f"IfcMapConversion.{attribute} must be finite.")
    scale = getattr(conversion, "Scale", None)
    if scale is not None and float(scale) == 0:
        raise LandXmlExportError("IfcMapConversion.Scale must not be zero for a terrain export.")
    for attribute in ("ScaleY", "ScaleZ"):
        if getattr(conversion, attribute, None) is not None:
            raise LandXmlExportError(
                f"IfcMapConversion.{attribute} is not supported; this producer requires one uniform Scale."
            )
    _normalised_map_direction(conversion)
    return conversion, source_context


def _project_length_to_metre(model: Any) -> float:
    projects = tuple(getattr(model, "by_type", lambda _: ())("IfcProject") or ())
    if len(projects) != 1:
        raise LandXmlExportError("IFC must contain exactly one IfcProject with length units.")
    units = tuple(getattr(getattr(projects[0], "UnitsInContext", None), "Units", ()) or ())
    length_units = [unit for unit in units if getattr(unit, "UnitType", None) == "LENGTHUNIT"]
    if len(length_units) != 1:
        raise LandXmlExportError("IfcProject.UnitsInContext must define exactly one LENGTHUNIT.")
    return _unit_to_metre(length_units[0])


def _unit_to_metre(unit: Any) -> float:
    return _unit_to_metre_with_guards(unit, set(), 0)


def _unit_to_metre_with_guards(unit: Any, visited: set[tuple[str, Any]], depth: int) -> float:
    if unit is None:
        raise LandXmlExportError("A length unit is missing.")
    if depth >= MAX_IFC_REFERENCE_DEPTH:
        raise LandXmlExportError(
            f"IfcConversionBasedUnit.UnitComponent chain exceeds the maximum depth of "
            f"{MAX_IFC_REFERENCE_DEPTH}."
        )
    marker = _entity_marker(unit)
    if marker in visited:
        raise LandXmlExportError("IfcConversionBasedUnit.UnitComponent chain contains a cycle.")
    visited.add(marker)
    if getattr(unit, "UnitType", None) != "LENGTHUNIT":
        raise LandXmlExportError(f"Expected LENGTHUNIT, got {getattr(unit, 'UnitType', None)}.")
    if _is_a(unit, "IfcSIUnit"):
        if getattr(unit, "Name", None) != "METRE":
            raise LandXmlExportError(f"Unsupported IFC SI length unit: {getattr(unit, 'Name', None)}.")
        prefixes = {
            None: 1.0, "EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9,
            "MEGA": 1e6, "KILO": 1e3, "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1,
            "CENTI": 1e-2, "MILLI": 1e-3, "MICRO": 1e-6, "NANO": 1e-9, "PICO": 1e-12,
        }
        prefix = getattr(unit, "Prefix", None)
        if prefix not in prefixes:
            raise LandXmlExportError(f"Unsupported IFC SI length prefix: {prefix}.")
        return prefixes[prefix]
    if _is_a(unit, "IfcConversionBasedUnit"):
        factor = getattr(getattr(unit, "ConversionFactor", None), "ValueComponent", None)
        component = getattr(getattr(unit, "ConversionFactor", None), "UnitComponent", None)
        if factor is None or component is None:
            raise LandXmlExportError("IfcConversionBasedUnit lacks a complete ConversionFactor.")
        converted = float(getattr(factor, "wrappedValue", factor)) * _unit_to_metre_with_guards(
            component, visited, depth + 1
        )
        if not math.isfinite(converted) or converted <= 0:
            raise LandXmlExportError("IfcConversionBasedUnit has an invalid length conversion factor.")
        return converted
    raise LandXmlExportError(f"Unsupported IFC length unit type: {_entity_type(unit)}.")


def _placement_matrix(placement: Any) -> tuple[tuple[float, float, float, float], ...]:
    relative_matrices = []
    visited = set()
    current = placement
    while current is not None:
        if len(relative_matrices) >= MAX_IFC_REFERENCE_DEPTH:
            raise LandXmlExportError(
                f"IfcLocalPlacement.PlacementRelTo chain exceeds the maximum depth of "
                f"{MAX_IFC_REFERENCE_DEPTH}."
            )
        marker = _entity_marker(current)
        if marker in visited:
            raise LandXmlExportError("IfcLocalPlacement.PlacementRelTo chain contains a cycle.")
        visited.add(marker)
        relative = getattr(current, "RelativePlacement", None)
        if relative is None:
            raise LandXmlExportError("IfcLocalPlacement has no RelativePlacement.")
        relative_matrices.append(_axis_placement_matrix(relative))
        current = getattr(current, "PlacementRelTo", None)
    result = _identity_matrix()
    for relative in reversed(relative_matrices):
        result = _matrix_multiply(result, relative)
    return result


def _axis_placement_matrix(axis_placement: Any) -> tuple[tuple[float, float, float, float], ...]:
    location = _three_components(getattr(getattr(axis_placement, "Location", None), "Coordinates", None), "placement Location")
    z_axis = _normalised_direction(getattr(getattr(axis_placement, "Axis", None), "DirectionRatios", None), (0.0, 0.0, 1.0), "Axis")
    x_axis = _normalised_direction(getattr(getattr(axis_placement, "RefDirection", None), "DirectionRatios", None), (1.0, 0.0, 0.0), "RefDirection")
    y_axis = _cross(z_axis, x_axis)
    if _length(y_axis) == 0:
        raise LandXmlExportError("IfcAxis2Placement3D Axis and RefDirection are parallel.")
    y_axis = _normalise(y_axis)
    x_axis = _normalise(_cross(y_axis, z_axis))
    return (
        (x_axis[0], y_axis[0], z_axis[0], location[0]),
        (x_axis[1], y_axis[1], z_axis[1], location[1]),
        (x_axis[2], y_axis[2], z_axis[2], location[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def _transform_point(matrix: Sequence[Sequence[float]], point: Sequence[float]) -> tuple[float, float, float]:
    return tuple(sum(matrix[row][column] * point[column] for column in range(3)) + matrix[row][3] for row in range(3))  # type: ignore[return-value]


def _require_explicit_scale_for_unit_change(conversion: Any, source_to_metre: float, map_to_metre: float) -> None:
    if getattr(conversion, "Scale", None) is None and not math.isclose(source_to_metre, map_to_metre):
        raise LandXmlExportError(
            "IfcMapConversion.Scale is required when project and MapUnit lengths differ. "
            "Scale is the combined local-to-map conversion; the exporter will not infer it."
        )


def _map_coordinate(local: tuple[float, float, float], conversion: Any, *, map_to_metre: float) -> tuple[float, float, float]:
    abscissa, ordinate = _normalised_map_direction(conversion)
    scale = float(getattr(conversion, "Scale", 1.0) if getattr(conversion, "Scale", None) is not None else 1.0)
    factor_x = float(getattr(conversion, "FactorX", 1.0) if getattr(conversion, "FactorX", None) is not None else 1.0)
    factor_y = float(getattr(conversion, "FactorY", 1.0) if getattr(conversion, "FactorY", None) is not None else 1.0)
    factor_z = float(getattr(conversion, "FactorZ", 1.0) if getattr(conversion, "FactorZ", None) is not None else 1.0)
    easting = float(conversion.Eastings) + scale * (abscissa * factor_x * local[0] - ordinate * factor_y * local[1])
    northing = float(conversion.Northings) + scale * (ordinate * factor_x * local[0] + abscissa * factor_y * local[1])
    elevation = float(conversion.OrthogonalHeight) + scale * factor_z * local[2]
    result = tuple(value * map_to_metre for value in (easting, northing, elevation))
    if not all(math.isfinite(value) for value in result):
        raise LandXmlExportError("IFC placement and map conversion produced non-finite map coordinates.")
    return result


def _normalised_map_direction(conversion: Any) -> tuple[float, float]:
    abscissa = float(
        getattr(conversion, "XAxisAbscissa", 1.0)
        if getattr(conversion, "XAxisAbscissa", None) is not None
        else 1.0
    )
    ordinate = float(
        getattr(conversion, "XAxisOrdinate", 0.0)
        if getattr(conversion, "XAxisOrdinate", None) is not None
        else 0.0
    )
    magnitude = math.hypot(abscissa, ordinate)
    if magnitude == 0:
        raise LandXmlExportError(
            "IfcMapConversion XAxisAbscissa and XAxisOrdinate must not both be zero."
        )
    return abscissa / magnitude, ordinate / magnitude


def _reject_nonidentity_world_coordinate_system(context: Any) -> None:
    world_coordinate_system = getattr(context, "WorldCoordinateSystem", None)
    if world_coordinate_system is None:
        raise LandXmlExportError(
            "Map-conversion source context has no WorldCoordinateSystem; export cannot prove its coordinates."
        )
    matrix = _axis_placement_matrix(world_coordinate_system)
    identity = _identity_matrix()
    if any(
        not math.isclose(matrix[row][column], identity[row][column], abs_tol=1e-12)
        for row in range(4)
        for column in range(4)
    ):
        raise LandXmlExportError(
            "Map-conversion source context has a non-identity WorldCoordinateSystem. "
            "This producer rejects it rather than risk applying the selected-context transform twice."
        )


def _validate_mesh(mesh: TerrainMesh) -> None:
    if len(mesh.vertices_enz) < 3:
        raise LandXmlExportError("Terrain TIN must contain at least three transformed vertices.")
    if not mesh.faces:
        raise LandXmlExportError("Terrain TIN must contain at least one authored face.")
    for vertex_number, vertex in enumerate(mesh.vertices_enz, start=1):
        if len(vertex) != 3 or not all(math.isfinite(value) for value in vertex):
            raise LandXmlExportError(f"Terrain vertex {vertex_number} is not a finite map coordinate.")
    for face_number, face in enumerate(mesh.faces, start=1):
        if len(face) != 3 or any(index < 1 or index > len(mesh.vertices_enz) for index in face):
            raise LandXmlExportError(f"Terrain face {face_number} references an undefined vertex.")
        _validate_triangle(
            tuple(mesh.vertices_enz[index - 1] for index in face),
            f"Terrain face {face_number}",
        )


def _validate_triangle(
    vertices: tuple[tuple[float, float, float], ...], label: str
) -> None:
    first, second, third = vertices
    first_to_second = tuple(second[index] - first[index] for index in range(3))
    first_to_third = tuple(third[index] - first[index] for index in range(3))
    cross_product = _cross(first_to_second, first_to_third)
    if _length(cross_product) <= 1e-24:
        raise LandXmlExportError(f"{label} is degenerate or collapses after coordinate conversion.")


def _tag(name: str) -> str:
    return f"{{{LANDXML_NAMESPACE}}}{name}"


def _reject_input_output_overlap(source: Path, destination: Path) -> None:
    """Refuse aliases before any IFC read or LandXML write can mutate input."""

    try:
        same_file = source.resolve() == destination.resolve() or (
            destination.exists() and source.samefile(destination)
        )
    except OSError as exc:
        raise LandXmlExportError(
            f"Could not resolve IFC input and LandXML output paths safely: {exc}"
        ) from exc
    if same_file:
        raise LandXmlExportError(
            "IFC input and LandXML output resolve to the same file. Choose a different output path; "
            "the source IFC will not be overwritten."
        )


def _format_coordinate(*values: float) -> str:
    return " ".join(format(value, ".12g") for value in values)


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _finite_attribute(entity: Any, attribute: str) -> None:
    if not _is_finite_number(getattr(entity, attribute, None)):
        raise LandXmlExportError(f"IfcMapConversion.{attribute} must be a finite number.")


def _required_text(value: Any, attribute: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LandXmlExportError(f"{attribute} is required; the exporter will not guess a CRS.")
    return value


def _entity_type(entity: Any) -> str:
    is_a = getattr(entity, "is_a", None)
    return is_a() if callable(is_a) else type(entity).__name__


def _is_a(entity: Any, name: str) -> bool:
    is_a = getattr(entity, "is_a", None)
    if not callable(is_a):
        return False
    try:
        return bool(is_a(name))
    except TypeError:
        return is_a() == name


def _same_entity(left: Any, right: Any) -> bool:
    if left is right or left == right:
        return True
    left_id = getattr(left, "id", None)
    right_id = getattr(right, "id", None)
    if callable(left_id) and callable(right_id):
        return left_id() == right_id()
    return False


def _entity_marker(entity: Any) -> tuple[str, Any]:
    identifier = getattr(entity, "id", None)
    if callable(identifier):
        return "ifc-id", identifier()
    return "object-id", id(entity)


def _terrain_name(terrain: Any, global_id: str) -> str:
    name = getattr(terrain, "Name", None)
    return name if isinstance(name, str) and name.strip() else f"Terrain_{global_id}"


def _three_components(values: Any, label: str) -> tuple[float, float, float]:
    if values is None or len(values) != 3:
        raise LandXmlExportError(f"IfcAxis2Placement3D {label} must have three components.")
    result = tuple(float(value) for value in values)
    if not all(math.isfinite(value) for value in result):
        raise LandXmlExportError(f"IfcAxis2Placement3D {label} must be finite.")
    return result


def _normalised_direction(values: Any, default: tuple[float, float, float], label: str) -> tuple[float, float, float]:
    return _normalise(_three_components(values, label) if values is not None else default)


def _normalise(vector: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude = _length(vector)
    if magnitude == 0:
        raise LandXmlExportError("IfcAxis2Placement3D direction must not be zero.")
    return tuple(value / magnitude for value in vector)  # type: ignore[return-value]


def _length(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def _cross(left: tuple[float, float, float], right: tuple[float, float, float]) -> tuple[float, float, float]:
    return (left[1] * right[2] - left[2] * right[1], left[2] * right[0] - left[0] * right[2], left[0] * right[1] - left[1] * right[0])


def _identity_matrix() -> tuple[tuple[float, float, float, float], ...]:
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def _matrix_multiply(left: Sequence[Sequence[float]], right: Sequence[Sequence[float]]) -> tuple[tuple[float, float, float, float], ...]:
    return tuple(tuple(sum(left[row][index] * right[index][column] for index in range(4)) for column in range(4)) for row in range(4))  # type: ignore[return-value]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the headless producer: no GUI, config CRS defaults, or heuristics."""

    parser = argparse.ArgumentParser(description="Export one selected IFC terrain TIN as LandXML 1.2.")
    parser.add_argument("ifc", type=Path, help="Input IFC file")
    parser.add_argument("output", type=Path, help="Output LandXML file")
    parser.add_argument("--terrain-global-id", required=True, help="GlobalId of the IfcGeographicElement terrain")
    parser.add_argument("--project-name", help="LandXML Project name (defaults to input filename)")
    arguments = parser.parse_args(argv)
    try:
        mesh = export_ifc_terrain_to_landxml(arguments.ifc, arguments.output, terrain_global_id=arguments.terrain_global_id, project_name=arguments.project_name)
    except LandXmlExportError as exc:
        parser.error(str(exc))
    print(f"Exported '{mesh.name}': {len(mesh.vertices_enz)} points, {len(mesh.faces)} authored faces.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
