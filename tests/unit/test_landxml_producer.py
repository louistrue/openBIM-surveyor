"""Synthetic contract tests for the explicit IFC terrain LandXML producer."""

from __future__ import annotations

import os
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from unittest import mock
import unittest
import xml.etree.ElementTree as ET

from src.core.converters.ifc_to_landxml import (
    LANDXML_NAMESPACE,
    MAX_IFC_REFERENCE_DEPTH,
    LandXmlExportError,
    TerrainSelection,
    build_landxml_document,
    export_ifc_terrain_to_landxml,
    produce_terrain_mesh,
    validate_landxml_bytes,
    write_validated_landxml,
)


class Entity(SimpleNamespace):
    """Small IFC-shaped test double; no customer IFC fixture is required."""

    def __init__(
        self, entity_type: str, *, supertypes: tuple[str, ...] = (), **attributes: object
    ) -> None:
        super().__init__(**attributes)
        self.entity_type = entity_type
        self.supertypes = supertypes

    def is_a(self, requested_type: str | None = None) -> str | bool:
        if requested_type is None:
            return self.entity_type
        return requested_type in (self.entity_type, *self.supertypes)


class SyntheticModel:
    def __init__(self, terrain: Entity, conversion: Entity | None) -> None:
        self.terrain = terrain
        self.conversion = conversion
        self.cartesian_points_requested = False
        millimetres = Entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix="MILLI")
        self.project = Entity("IfcProject", UnitsInContext=Entity("IfcUnitAssignment", Units=[millimetres]))

    def by_guid(self, global_id: str) -> Entity | None:
        return self.terrain if global_id == self.terrain.GlobalId else None

    def by_type(self, entity_type: str) -> list[Entity]:
        if entity_type == "IfcMapConversion":
            return [] if self.conversion is None else [self.conversion]
        if entity_type == "IfcProject":
            return [self.project]
        if entity_type == "IfcCartesianPoint":
            self.cartesian_points_requested = True
            raise AssertionError("Producer must not inspect all IfcCartesianPoint entities")
        return []


def synthetic_model(*, selected_type: str = "IfcGeographicElement", conversion: bool = True) -> SyntheticModel:
    context = Entity(
        "IfcGeometricRepresentationContext",
        WorldCoordinateSystem=Entity(
            "IfcAxis2Placement3D",
            Location=Entity("IfcCartesianPoint", Coordinates=(0, 0, 0)),
            Axis=None,
            RefDirection=None,
        ),
    )
    face_set = Entity(
        "IfcTriangulatedFaceSet",
        Coordinates=Entity("IfcCartesianPointList3D", CoordList=[(0, 0, 0), (1000, 0, 0), (0, 1000, 0), (1000, 1000, 0)]),
        CoordIndex=[(1, 2, 3), (2, 4, 3)],
    )
    representation = Entity("IfcShapeRepresentation", ContextOfItems=context, Items=[face_set])
    placement = Entity(
        "IfcLocalPlacement",
        PlacementRelTo=None,
        RelativePlacement=Entity(
            "IfcAxis2Placement3D",
            Location=Entity("IfcCartesianPoint", Coordinates=(1000, 2000, 3000)),
            Axis=None,
            RefDirection=None,
        ),
    )
    terrain = Entity(
        selected_type,
        GlobalId="terrain-global-id",
        Name="Author Terrain",
        Representation=Entity("IfcProductDefinitionShape", Representations=[representation]),
        ObjectPlacement=placement,
    )
    map_unit = Entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix=None)
    operation = Entity(
        "IfcMapConversion",
        SourceCRS=context,
        TargetCRS=Entity("IfcProjectedCRS", Name="EPSG:3006", MapUnit=map_unit),
        Eastings=500000,
        Northings=6400000,
        OrthogonalHeight=10,
        XAxisAbscissa=1,
        XAxisOrdinate=0,
        # IFC MapConversion.Scale is the combined project-unit-to-map-unit scale.
        Scale=0.001,
    ) if conversion else None
    return SyntheticModel(terrain, operation)


class LandXmlProducerContractTests(unittest.TestCase):
    def test_rejects_identical_or_resolved_equivalent_input_output_before_opening_ifc(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "terrain.ifc"
            source.write_bytes(b"original IFC bytes")
            alias = Path(directory) / "nested" / ".." / "terrain.ifc"

            with self.assertRaisesRegex(LandXmlExportError, "resolve to the same file"):
                export_ifc_terrain_to_landxml(source, alias, terrain_global_id="terrain-global-id")

            self.assertEqual(source.read_bytes(), b"original IFC bytes")
            hard_link = Path(directory) / "terrain-alias.xml"
            os.link(source, hard_link)
            with self.assertRaisesRegex(LandXmlExportError, "resolve to the same file"):
                export_ifc_terrain_to_landxml(source, hard_link, terrain_global_id="terrain-global-id")
            self.assertEqual(source.read_bytes(), b"original IFC bytes")

    def test_by_guid_runtime_error_is_actionable_and_never_mutates_output(self) -> None:
        class RuntimeFailureModel:
            def by_guid(self, _: str) -> None:
                raise RuntimeError("entity instance is invalid")

        with TemporaryDirectory() as directory:
            source = Path(directory) / "terrain.ifc"
            output = Path(directory) / "terrain.xml"
            source.write_bytes(b"input IFC")
            output.write_bytes(b"previous LandXML")
            fake_ifcopenshell = SimpleNamespace(open=lambda _: RuntimeFailureModel())

            with mock.patch.dict("sys.modules", {"ifcopenshell": fake_ifcopenshell}):
                with self.assertRaisesRegex(LandXmlExportError, "Could not resolve terrain GlobalId"):
                    export_ifc_terrain_to_landxml(source, output, terrain_global_id="terrain-global-id")

            self.assertEqual(output.read_bytes(), b"previous LandXML")

    def test_coordinate_contract_applies_units_placement_and_map_conversion_once(self) -> None:
        model = synthetic_model()

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))
        document = build_landxml_document(mesh, project_name="synthetic")

        self.assertEqual(mesh.vertices_enz[0], (500001.0, 6400002.0, 13.0))
        self.assertEqual(mesh.vertices_enz[3], (500002.0, 6400003.0, 13.0))
        root = ET.fromstring(document)
        namespace = {"landxml": LANDXML_NAMESPACE}
        points = root.findall(".//landxml:P", namespace)
        # The source values were IFC X/Y/Z. LandXML is explicitly N/E/Z.
        self.assertEqual(points[0].text, "6400002 500001 13")
        self.assertEqual(points[3].text, "6400003 500002 13")
        metric = root.find(".//landxml:Metric", namespace)
        self.assertEqual(metric.get("linearUnit"), "meter")
        self.assertEqual(metric.get("elevationUnit"), "meter")
        validate_landxml_bytes(document)

    def test_preserves_authored_face_order_and_never_reads_unrelated_points(self) -> None:
        model = synthetic_model()

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))
        document = build_landxml_document(mesh, project_name="synthetic")

        root = ET.fromstring(document)
        namespace = {"landxml": LANDXML_NAMESPACE}
        self.assertEqual([face.text for face in root.findall(".//landxml:F", namespace)], ["1 2 3", "2 4 3"])
        self.assertFalse(model.cartesian_points_requested)

    def test_composes_parent_and_product_placements_before_map_conversion(self) -> None:
        model = synthetic_model()
        model.terrain.ObjectPlacement.PlacementRelTo = Entity(
            "IfcLocalPlacement",
            PlacementRelTo=None,
            RelativePlacement=Entity(
                "IfcAxis2Placement3D",
                Location=Entity("IfcCartesianPoint", Coordinates=(500, -1000, 250)),
                Axis=None,
                RefDirection=None,
            ),
        )

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

        self.assertEqual(mesh.vertices_enz[0], (500001.5, 6400001.0, 13.25))

    def test_rejects_self_and_two_node_placement_cycles(self) -> None:
        self_cycle = synthetic_model()
        placement = self_cycle.terrain.ObjectPlacement
        placement.PlacementRelTo = placement
        with self.assertRaisesRegex(LandXmlExportError, "PlacementRelTo chain contains a cycle"):
            produce_terrain_mesh(self_cycle, TerrainSelection("terrain-global-id"))

        two_node_cycle = synthetic_model()
        first = two_node_cycle.terrain.ObjectPlacement
        second = Entity(
            "IfcLocalPlacement",
            PlacementRelTo=first,
            RelativePlacement=first.RelativePlacement,
        )
        first.PlacementRelTo = second
        with self.assertRaisesRegex(LandXmlExportError, "PlacementRelTo chain contains a cycle"):
            produce_terrain_mesh(two_node_cycle, TerrainSelection("terrain-global-id"))

    def test_rejects_placement_chain_past_bounded_depth(self) -> None:
        model = synthetic_model()
        current = model.terrain.ObjectPlacement
        for _ in range(MAX_IFC_REFERENCE_DEPTH):
            parent = Entity(
                "IfcLocalPlacement",
                PlacementRelTo=None,
                RelativePlacement=current.RelativePlacement,
            )
            current.PlacementRelTo = parent
            current = parent

        with self.assertRaisesRegex(LandXmlExportError, "PlacementRelTo chain exceeds the maximum depth"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_normalises_map_direction_before_applying_conversion(self) -> None:
        model = synthetic_model()
        model.conversion.XAxisAbscissa = 3
        model.conversion.XAxisOrdinate = 4

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

        self.assertEqual(mesh.vertices_enz[0], (499999.0, 6400002.0, 13.0))

    def test_rejects_zero_map_direction(self) -> None:
        model = synthetic_model()
        model.conversion.XAxisAbscissa = 0
        model.conversion.XAxisOrdinate = 0

        with self.assertRaisesRegex(LandXmlExportError, "must not both be zero"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_nonidentity_map_context_world_coordinate_system(self) -> None:
        model = synthetic_model()
        model.conversion.SourceCRS.WorldCoordinateSystem.Location.Coordinates = (1, 0, 0)

        with self.assertRaisesRegex(LandXmlExportError, "non-identity WorldCoordinateSystem"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_resolves_map_conversion_on_body_subcontext_parent(self) -> None:
        model = synthetic_model()
        parent_context = model.conversion.SourceCRS
        body_context = Entity("IfcGeometricRepresentationSubContext", ParentContext=parent_context)
        model.terrain.Representation.Representations[0].ContextOfItems = body_context

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

        self.assertEqual(mesh.vertices_enz[0], (500001.0, 6400002.0, 13.0))

    def test_applies_pn_index_before_writing_faces(self) -> None:
        model = synthetic_model()
        face_set = model.terrain.Representation.Representations[0].Items[0]
        face_set.PnIndex = (4, 1, 2, 3)

        mesh = produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))
        document = build_landxml_document(mesh, project_name="synthetic")
        root = ET.fromstring(document)
        namespace = {"landxml": LANDXML_NAMESPACE}

        self.assertEqual(mesh.vertices_enz[0], (500002.0, 6400003.0, 13.0))
        self.assertEqual([face.text for face in root.findall(".//landxml:F", namespace)], ["1 2 3", "2 4 3"])

    def test_refuses_inherited_triangulated_irregular_network_before_flags_become_visible_faces(self) -> None:
        model = synthetic_model()
        face_set = model.terrain.Representation.Representations[0].Items[0]
        irregular_network = Entity(
            "IfcTriangulatedIrregularNetwork",
            supertypes=("IfcTriangulatedFaceSet",),
            Coordinates=face_set.Coordinates,
            CoordIndex=face_set.CoordIndex,
            Flags=(-2, -1),
        )
        model.terrain.Representation.Representations[0].Items[0] = irregular_network

        self.assertTrue(irregular_network.is_a("IfcTriangulatedFaceSet"))
        with self.assertRaisesRegex(LandXmlExportError, "Flags can mark faces invisible or define voids"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_invalid_pn_index_and_pn_index_collapsed_triangle(self) -> None:
        invalid_model = synthetic_model()
        invalid_model.terrain.Representation.Representations[0].Items[0].PnIndex = (1, 2, 5, 3)
        with self.assertRaisesRegex(LandXmlExportError, "PnIndex references"):
            produce_terrain_mesh(invalid_model, TerrainSelection("terrain-global-id"))

        collapsed_model = synthetic_model()
        collapsed_model.terrain.Representation.Representations[0].Items[0].PnIndex = (1, 1, 2, 3)
        with self.assertRaisesRegex(LandXmlExportError, "degenerate or collapses"):
            produce_terrain_mesh(collapsed_model, TerrainSelection("terrain-global-id"))

    def test_rejects_building_global_id_even_when_it_has_a_tin(self) -> None:
        model = synthetic_model(selected_type="IfcSlab")

        with self.assertRaisesRegex(LandXmlExportError, "not IfcGeographicElement"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_missing_map_conversion_instead_of_guessing_crs(self) -> None:
        model = synthetic_model(conversion=False)

        with self.assertRaisesRegex(LandXmlExportError, "will not guess a CRS"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_omitted_combined_scale_when_project_and_map_units_differ(self) -> None:
        model = synthetic_model()
        model.conversion.Scale = None

        with self.assertRaisesRegex(LandXmlExportError, "Scale is required"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_zero_map_conversion_scale(self) -> None:
        model = synthetic_model()
        model.conversion.Scale = 0

        with self.assertRaisesRegex(LandXmlExportError, "Scale must not be zero"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_rejects_self_and_two_node_conversion_unit_cycles(self) -> None:
        def conversion_unit(component: Entity | None = None) -> Entity:
            return Entity(
                "IfcConversionBasedUnit",
                UnitType="LENGTHUNIT",
                ConversionFactor=Entity("IfcMeasureWithUnit", ValueComponent=1, UnitComponent=component),
            )

        self_cycle = synthetic_model()
        self_unit = conversion_unit()
        self_unit.ConversionFactor.UnitComponent = self_unit
        self_cycle.conversion.TargetCRS.MapUnit = self_unit
        with self.assertRaisesRegex(LandXmlExportError, "UnitComponent chain contains a cycle"):
            produce_terrain_mesh(self_cycle, TerrainSelection("terrain-global-id"))

        two_node_cycle = synthetic_model()
        first = conversion_unit()
        second = conversion_unit(first)
        first.ConversionFactor.UnitComponent = second
        two_node_cycle.conversion.TargetCRS.MapUnit = first
        with self.assertRaisesRegex(LandXmlExportError, "UnitComponent chain contains a cycle"):
            produce_terrain_mesh(two_node_cycle, TerrainSelection("terrain-global-id"))

    def test_rejects_conversion_unit_chain_past_bounded_depth(self) -> None:
        model = synthetic_model()
        root = Entity(
            "IfcConversionBasedUnit",
            UnitType="LENGTHUNIT",
            ConversionFactor=Entity("IfcMeasureWithUnit", ValueComponent=1, UnitComponent=None),
        )
        current = root
        for _ in range(MAX_IFC_REFERENCE_DEPTH):
            child = Entity(
                "IfcConversionBasedUnit",
                UnitType="LENGTHUNIT",
                ConversionFactor=Entity("IfcMeasureWithUnit", ValueComponent=1, UnitComponent=None),
            )
            current.ConversionFactor.UnitComponent = child
            current = child
        current.ConversionFactor.UnitComponent = Entity(
            "IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE", Prefix=None
        )
        model.conversion.TargetCRS.MapUnit = root

        with self.assertRaisesRegex(LandXmlExportError, "UnitComponent chain exceeds the maximum depth"):
            produce_terrain_mesh(model, TerrainSelection("terrain-global-id"))

    def test_generated_byte_validation_catches_damaged_faces(self) -> None:
        mesh = produce_terrain_mesh(synthetic_model(), TerrainSelection("terrain-global-id"))
        broken = build_landxml_document(mesh, project_name="synthetic").replace(b">1 2 3<", b">1 2 99<", 1)

        with self.assertRaisesRegex(LandXmlExportError, "does not reference"):
            validate_landxml_bytes(broken)

    def test_generated_byte_validation_catches_post_serialization_collapsed_triangle(self) -> None:
        mesh = produce_terrain_mesh(synthetic_model(), TerrainSelection("terrain-global-id"))
        root = ET.fromstring(build_landxml_document(mesh, project_name="synthetic"))
        points = root.findall(f".//{{{LANDXML_NAMESPACE}}}P")
        points[1].text = points[0].text
        collapsed = ET.tostring(root, encoding="utf-8", xml_declaration=True)

        with self.assertRaisesRegex(LandXmlExportError, "degenerate or collapses"):
            validate_landxml_bytes(collapsed)

    def test_writer_validates_before_replacing_output(self) -> None:
        mesh = produce_terrain_mesh(synthetic_model(), TerrainSelection("terrain-global-id"))
        valid = build_landxml_document(mesh, project_name="synthetic")
        invalid = valid.replace(b">1 2 3<", b">1 2 99<", 1)
        with TemporaryDirectory() as directory:
            output = Path(directory) / "terrain.xml"
            output.write_bytes(b"previous deliverable")

            with self.assertRaises(LandXmlExportError):
                write_validated_landxml(output, invalid)

            self.assertEqual(output.read_bytes(), b"previous deliverable")
            write_validated_landxml(output, valid)
            self.assertEqual(output.read_bytes(), valid)

    def test_concurrent_writers_use_unique_atomic_temp_files(self) -> None:
        mesh = produce_terrain_mesh(synthetic_model(), TerrainSelection("terrain-global-id"))
        first = build_landxml_document(mesh, project_name="first")
        second = build_landxml_document(mesh, project_name="second")
        failures = []
        barrier = Barrier(2)

        def write(document: bytes) -> None:
            try:
                barrier.wait()
                write_validated_landxml(output, document)
            except Exception as exc:  # pragma: no cover - asserted below
                failures.append(exc)

        with TemporaryDirectory() as directory:
            output = Path(directory) / "terrain.xml"
            first_thread = Thread(target=write, args=(first,))
            second_thread = Thread(target=write, args=(second,))
            first_thread.start()
            second_thread.start()
            first_thread.join()
            second_thread.join()

            self.assertEqual(failures, [])
            self.assertIn(output.read_bytes(), {first, second})
            self.assertEqual(list(Path(directory).glob(".terrain.xml.*.tmp")), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
