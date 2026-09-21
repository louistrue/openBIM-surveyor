"""End-to-end invariants for the CSV survey-point handoff.

The test creates its own synthetic client-format CSV and writes only below a
temporary directory. It does not use or bless the repository's client-labelled
files as a fixture or a machine-control reference.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from experiments.prototypes import complete_client_workflow
from experiments.prototypes.complete_client_workflow import (
    default_config,
    resolve_output_directory,
    run_workflow,
)
from src.core.converters.ifc_to_landxml import (
    LANDXML_NAMESPACE,
    LandXmlExportError,
    TerrainMesh,
    build_landxml_document,
    validate_landxml_bytes,
)


HAS_CSV_TO_IFC_DEPENDENCIES = all(
    importlib.util.find_spec(package) is not None
    for package in ("pandas", "ifcopenshell")
)


def pset_values(annotation: object) -> dict[str, object]:
    """Read the SurveyData values emitted by the actual IFC converter."""

    for relationship in annotation.IsDefinedBy:
        property_set = relationship.RelatingPropertyDefinition
        if property_set.Name != "SurveyData":
            continue
        return {
            property_.Name: property_.NominalValue.wrappedValue
            for property_ in property_set.HasProperties
        }
    raise AssertionError(f"IfcAnnotation {annotation.GlobalId} has no SurveyData property set")


class ClientWorkflowIntegrationTests(unittest.TestCase):
    @staticmethod
    def write_synthetic_csv(path: Path, point_id: str) -> None:
        """Write a minimal independent client-format input for workflow tests."""

        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(("localId", "y", "x", "z", "code", "description"))
            writer.writerow((point_id, 6400000, 500000, 10, "CONTROL", point_id))

    def test_rejects_repository_sample_output_directories(self) -> None:
        repository_root = Path(__file__).parents[2]
        for directory in (repository_root / "data" / "processed", repository_root / "data" / "output"):
            with self.subTest(directory=directory):
                with self.assertRaisesRegex(ValueError, "tracked output directory"):
                    resolve_output_directory(directory)

    def test_existing_output_directory_is_never_reused(self) -> None:
        """Directory publication needs a new destination to remain all-or-nothing."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            input_csv = temporary / "survey.csv"
            self.write_synthetic_csv(input_csv, "control")
            output_dir = temporary / "existing-output"
            output_dir.mkdir()

            with self.assertRaisesRegex(FileExistsError, "Refusing to overwrite existing"):
                run_workflow(input_csv, output_dir, config=default_config())

            self.assertEqual(list(output_dir.iterdir()), [])

    @unittest.skipUnless(HAS_CSV_TO_IFC_DEPENDENCIES, "requires pandas and ifcopenshell")
    def test_synthetic_csv_points_correspond_to_ifc_annotations_and_declared_crs(self) -> None:
        """Point ID, metadata, local/projected coordinates, CRS and metre unit agree."""

        import ifcopenshell

        source_points = {
            "100": (1234.125, 5678.500, 18.25, "EDGE", "north edge"),
            "101": (1235.375, 5680.000, 19.75, "TREE", "oak"),
            "102": (1234.875, 5679.250, 18.75, "UTILITY", "cover"),
        }
        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            input_csv = temporary / "synthetic_client.csv"
            with input_csv.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle, delimiter=";")
                writer.writerow(("localId", "y", "x", "z", "code", "description"))
                for point_id, (x, y, z, code, description) in source_points.items():
                    writer.writerow((point_id, y, x, z, code, description))

            summary = run_workflow(input_csv, temporary / "outputs", config=default_config())
            outputs = {name: Path(path) for name, path in summary["outputs"].items()}
            self.assertEqual(summary["landxml"]["status"], "not_requested")
            self.assertTrue(outputs["ifc"].is_file())

            with outputs["processed_csv"].open(newline="", encoding="utf-8") as handle:
                processed = {row["ID"]: row for row in csv.DictReader(handle) if row["ID"] != "ORIGIN"}
            self.assertEqual(set(processed), set(source_points))

            transform = json.loads(outputs["transform_info"].read_text(encoding="utf-8"))
            model = ifcopenshell.open(str(outputs["ifc"]))
            annotations = {
                pset_values(annotation)["ID"]: annotation
                for annotation in model.by_type("IfcAnnotation")
            }
            self.assertEqual(set(annotations), set(source_points))
            for point_id, (source_x, source_y, source_z, code, description) in source_points.items():
                with self.subTest(point=point_id):
                    properties = pset_values(annotations[point_id])
                    placement = annotations[point_id].ObjectPlacement.RelativePlacement.Location.Coordinates
                    self.assertEqual(properties["Code"], code)
                    self.assertEqual(properties["Description"], description)
                    self.assertAlmostEqual(float(properties["LocalX"]), float(processed[point_id]["X"]), places=3)
                    self.assertAlmostEqual(float(properties["LocalY"]), float(processed[point_id]["Y"]), places=3)
                    self.assertAlmostEqual(float(properties["LocalZ"]), float(processed[point_id]["Z"]), places=3)
                    self.assertAlmostEqual(float(placement[0]), float(processed[point_id]["X"]), places=3)
                    self.assertAlmostEqual(float(placement[1]), float(processed[point_id]["Y"]), places=3)
                    self.assertAlmostEqual(float(placement[2]), float(processed[point_id]["Z"]), places=3)
                    self.assertLessEqual(abs(float(properties["OriginalX"]) - source_x), 0.0005)
                    self.assertLessEqual(abs(float(properties["OriginalY"]) - source_y), 0.0005)
                    self.assertLessEqual(abs(float(properties["OriginalZ"]) - source_z), 0.0005)

            length_units = [
                unit for unit in model.by_type("IfcSIUnit") if unit.UnitType == "LENGTHUNIT"
            ]
            self.assertEqual(len(length_units), 1)
            self.assertEqual(length_units[0].Name, "METRE")
            self.assertIsNone(length_units[0].Prefix)
            conversion = model.by_type("IfcMapConversion")[0]
            self.assertEqual(conversion.TargetCRS.Name, "EPSG:3006 SWEREF99 TM")
            self.assertAlmostEqual(conversion.Eastings, transform["local_origin"]["x"])
            self.assertAlmostEqual(conversion.Northings, transform["local_origin"]["y"])
            self.assertAlmostEqual(conversion.OrthogonalHeight, transform["local_origin"]["z"])

    @unittest.skipUnless(HAS_CSV_TO_IFC_DEPENDENCIES, "requires pandas and ifcopenshell")
    def test_concurrent_runs_reserve_one_output_directory_exclusively(self) -> None:
        """Regression for #5051: concurrent same-target runs never interleave artifacts."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            first_input = temporary / "first" / "survey.csv"
            second_input = temporary / "second" / "survey.csv"
            first_input.parent.mkdir()
            second_input.parent.mkdir()
            self.write_synthetic_csv(first_input, "first")
            self.write_synthetic_csv(second_input, "second")
            output_dir = temporary / "shared-output"

            barrier = Barrier(2)
            original_reserve = complete_client_workflow.reserve_workflow_workspace
            results: list[dict[str, object]] = []
            failures: list[BaseException] = []

            def reserve_at_once(destination: Path):
                barrier.wait()
                return original_reserve(destination)

            def run(input_csv: Path) -> None:
                try:
                    results.append(run_workflow(input_csv, output_dir, config=default_config()))
                except BaseException as exc:  # asserted below, after both worker threads join
                    failures.append(exc)

            with mock.patch.object(
                complete_client_workflow, "reserve_workflow_workspace", side_effect=reserve_at_once
            ):
                workers = [Thread(target=run, args=(input_csv,)) for input_csv in (first_input, second_input)]
                for worker in workers:
                    worker.start()
                for worker in workers:
                    worker.join()

            self.assertEqual(len(results), 1)
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], FileExistsError)
            persisted = json.loads((output_dir / "workflow_summary.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["input"], results[0]["input"])
            self.assertFalse(
                (output_dir / complete_client_workflow.RESERVATION_FILENAME).exists(),
                "the completed workflow must release its exclusive reservation",
            )

    def test_destination_reservation_prevents_the_publish_time_directory_race(self) -> None:
        """Regression for #5051: a contender cannot create the destination after staging starts."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            output_dir = temporary / "reserved-output"
            workspace = complete_client_workflow.reserve_workflow_workspace(output_dir)
            staged_artifact = workspace.staging / "artifact.txt"
            staged_artifact.write_text("complete artifact\n", encoding="utf-8")
            (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
            original_link = complete_client_workflow.os.link

            def contend_for_destination(source: Path, target: Path) -> None:
                with self.assertRaises(FileExistsError):
                    output_dir.mkdir()
                return original_link(source, target)

            try:
                with mock.patch.object(
                    complete_client_workflow.os,
                    "link",
                    side_effect=contend_for_destination,
                ):
                    complete_client_workflow.publish_workflow_workspace(workspace)
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

            self.assertEqual(
                (output_dir / "artifact.txt").read_text(encoding="utf-8"),
                "complete artifact\n",
            )
            self.assertFalse((output_dir / complete_client_workflow.RESERVATION_FILENAME).exists())

    @unittest.skipUnless(HAS_CSV_TO_IFC_DEPENDENCIES, "requires pandas and ifcopenshell")
    def test_failed_terrain_export_leaves_no_published_or_staged_artifacts(self) -> None:
        """Regression for #5051: a failed optional export rolls back the complete run."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            input_csv = temporary / "survey.csv"
            self.write_synthetic_csv(input_csv, "control")
            output_dir = temporary / "failed-output"

            with mock.patch.object(
                complete_client_workflow,
                "export_ifc_terrain_to_landxml",
                side_effect=LandXmlExportError("synthetic terrain rejection"),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic terrain rejection"):
                    run_workflow(
                        input_csv,
                        output_dir,
                        terrain_ifc=input_csv,
                        terrain_global_id="terrain-global-id",
                        config=default_config(),
                    )

            self.assertFalse(output_dir.exists())
            self.assertEqual(list(temporary.glob(".failed-output.bonsai-topo-stage-*")), [])

    def test_landxml_serialized_bytes_are_well_formed_and_declare_metre_units(self) -> None:
        """The supported terrain handoff validates XML bytes and its constrained schema shape."""

        mesh = TerrainMesh(
            name="Synthetic terrain",
            vertices_enz=((500000.0, 6400000.0, 10.0), (500001.0, 6400000.0, 11.0), (500000.0, 6400001.0, 12.0)),
            faces=((1, 2, 3),),
            crs_name="EPSG:3006",
        )
        document = build_landxml_document(mesh, project_name="synthetic")
        validate_landxml_bytes(document)
        root = ET.fromstring(document)
        namespace = {"landxml": LANDXML_NAMESPACE}
        self.assertEqual(root.tag, f"{{{LANDXML_NAMESPACE}}}LandXML")
        metric = root.find(".//landxml:Metric", namespace)
        self.assertIsNotNone(metric)
        self.assertEqual(metric.get("linearUnit"), "meter")
        self.assertEqual(metric.get("elevationUnit"), "meter")
        self.assertEqual(root.find("landxml:CoordinateSystem", namespace).get("name"), "EPSG:3006")
        point = root.find(".//landxml:P", namespace)
        self.assertEqual(point.text, "6400000 500000 10")


if __name__ == "__main__":
    unittest.main()
