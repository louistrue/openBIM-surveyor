"""End-to-end invariants for the CSV survey-point handoff.

The test creates its own synthetic client-format CSV and writes only below a
temporary directory. It does not use or bless the repository's client-labelled
files as a fixture or a machine-control reference.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
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
            self.assertTrue((output_dir / complete_client_workflow.INCOMPLETE_FILENAME).is_file())
            self.assertEqual(
                complete_client_workflow.verify_workflow_completion(output_dir)["format"],
                "bonsai-topo-workflow-completion-v1",
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
            self.assertTrue((output_dir / complete_client_workflow.INCOMPLETE_FILENAME).is_file())
            self.assertTrue((output_dir / complete_client_workflow.COMPLETION_FILENAME).is_file())
            complete_client_workflow.verify_workflow_completion(output_dir)

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

            self.assertTrue(output_dir.is_dir())
            self.assertTrue((output_dir / complete_client_workflow.INCOMPLETE_FILENAME).is_file())
            self.assertEqual(
                list(output_dir.iterdir()),
                [output_dir / complete_client_workflow.INCOMPLETE_FILENAME],
            )
            self.assertEqual(list(temporary.glob(".failed-output.bonsai-topo-stage-*")), [])

    def test_forged_reservation_symlink_cannot_overwrite_external_content(self) -> None:
        """Regression for #5051: marker creation must not follow a forged symlink."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            destination = temporary / "output"
            external = temporary / "external.txt"
            external.write_text("external content\n", encoding="utf-8")
            marker = destination / complete_client_workflow.INCOMPLETE_FILENAME
            original_open = complete_client_workflow.os.open

            def forge_marker(path, flags, mode=0o777):
                if Path(path) == marker and flags & complete_client_workflow.os.O_EXCL:
                    os.symlink(external, marker)
                return original_open(path, flags, mode)

            with mock.patch.object(complete_client_workflow.os, "open", side_effect=forge_marker):
                with self.assertRaises(FileExistsError):
                    complete_client_workflow.reserve_workflow_workspace(destination)

            self.assertEqual(external.read_text(encoding="utf-8"), "external content\n")
            self.assertTrue(marker.is_symlink())

    def test_forged_summary_stays_incomplete_and_is_not_replaced(self) -> None:
        """Regression for #5051: a contender's ready marker cannot be overwritten."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                (workspace.staging / "artifact.txt").write_text("ours\n", encoding="utf-8")
                (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
                forged_summary = workspace.destination / "workflow_summary.json"
                forged_summary.write_text("forged\n", encoding="utf-8")

                with self.assertRaises(FileExistsError):
                    complete_client_workflow.publish_workflow_workspace(workspace)

                self.assertEqual(forged_summary.read_text(encoding="utf-8"), "forged\n")
                self.assertEqual(
                    (workspace.destination / "artifact.txt").read_text(encoding="utf-8"), "ours\n"
                )
                self.assertTrue(workspace.reservation.is_file())
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_retained_reservation_is_provenance_not_the_ready_condition(self) -> None:
        """Readiness comes from the immutable completion manifest, not marker removal."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                (workspace.staging / "artifact.txt").write_text("ours\n", encoding="utf-8")
                (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
                workspace.reservation.write_text("token=forged\nstate=incomplete\n", encoding="ascii")

                complete_client_workflow.publish_workflow_workspace(workspace)
                completion = complete_client_workflow.verify_workflow_completion(workspace.destination)
                self.assertEqual(completion["reservation_token"], workspace.reservation_token)
                self.assertTrue((workspace.destination / "artifact.txt").is_file())
                self.assertTrue(workspace.reservation.is_file())
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_publish_failure_never_deletes_a_substituted_destination_file(self) -> None:
        """Regression for #5051: failure cleanup must not unlink destination artifacts."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                first = workspace.staging / "first.txt"
                second = workspace.staging / "second.txt"
                first.write_text("ours\n", encoding="utf-8")
                second.write_text("second\n", encoding="utf-8")
                (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
                (workspace.destination / "second.txt").write_text("contender\n", encoding="utf-8")
                external = temporary / "external.txt"
                external.write_text("external content\n", encoding="utf-8")
                first_target = workspace.destination / "first.txt"
                original_link = complete_client_workflow.os.link

                def substitute_before_second_link(source, target):
                    if Path(source) == second:
                        os.replace(external, first_target)
                    return original_link(source, target)

                with mock.patch.object(
                    complete_client_workflow.os, "link", side_effect=substitute_before_second_link
                ):
                    with self.assertRaises(FileExistsError):
                        complete_client_workflow.publish_workflow_workspace(workspace)

                self.assertFalse(external.exists())
                self.assertEqual(first_target.read_text(encoding="utf-8"), "external content\n")
                self.assertTrue(workspace.reservation.is_file())
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_staging_substitution_fails_before_a_completion_manifest_is_published(self) -> None:
        """Regression for #5051: a replaced stage cannot become a ready handoff."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            orphaned_stage = temporary / "orphaned-stage"
            os.replace(workspace.staging, orphaned_stage)
            workspace.staging.mkdir()
            (workspace.staging / "artifact.txt").write_text("forged\n", encoding="utf-8")
            (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")

            try:
                with self.assertRaisesRegex(RuntimeError, "staging is no longer owned"):
                    complete_client_workflow.publish_workflow_workspace(workspace)
                self.assertFalse((workspace.destination / complete_client_workflow.COMPLETION_FILENAME).exists())
                self.assertEqual((workspace.staging / "artifact.txt").read_text(encoding="utf-8"), "forged\n")
            finally:
                with self.assertRaisesRegex(RuntimeError, "staging is no longer owned"):
                    complete_client_workflow.release_workflow_workspace(workspace)
            self.assertTrue(orphaned_stage.is_dir())

    def test_summary_injection_fails_before_completion_manifest_is_published(self) -> None:
        """Regression for #5051: replacement of a linked summary prevents readiness."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                artifact = workspace.staging / "artifact.txt"
                summary = workspace.staging / "workflow_summary.json"
                artifact.write_text("ours\n", encoding="utf-8")
                summary.write_text('{"ours": true}\n', encoding="utf-8")
                forged = temporary / "forged-summary.json"
                forged.write_text('{"forged": true}\n', encoding="utf-8")
                original_link = complete_client_workflow.os.link

                def replace_summary_after_link(source: Path, target: Path) -> None:
                    original_link(source, target)
                    if Path(source) == summary:
                        os.replace(forged, workspace.destination / "workflow_summary.json")

                with mock.patch.object(
                    complete_client_workflow.os, "link", side_effect=replace_summary_after_link
                ):
                    with self.assertRaisesRegex(RuntimeError, "does not match|changed while verifying"):
                        complete_client_workflow.publish_workflow_workspace(workspace)

                self.assertEqual(
                    (workspace.destination / "workflow_summary.json").read_text(encoding="utf-8"),
                    '{"forged": true}\n',
                )
                self.assertFalse((workspace.destination / complete_client_workflow.COMPLETION_FILENAME).exists())
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_marker_path_substitution_never_deletes_external_content(self) -> None:
        """Regression for #5051: no publication path unlinks a substituted marker."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                (workspace.staging / "artifact.txt").write_text("ours\n", encoding="utf-8")
                (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
                external = temporary / "external.txt"
                external.write_text("external content\n", encoding="utf-8")
                original_link = complete_client_workflow.os.link

                def replace_marker_before_completion(source: Path, target: Path) -> None:
                    original_link(source, target)
                    if Path(source).name == "workflow_summary.json":
                        try:
                            os.replace(external, workspace.reservation)
                        except PermissionError:
                            # The retained Windows descriptor denies the swap outright.
                            pass

                with mock.patch.object(
                    complete_client_workflow.os, "link", side_effect=replace_marker_before_completion
                ):
                    complete_client_workflow.publish_workflow_workspace(workspace)

                if external.exists():
                    self.assertEqual(external.read_text(encoding="utf-8"), "external content\n")
                else:
                    self.assertEqual(workspace.reservation.read_text(encoding="utf-8"), "external content\n")
                complete_client_workflow.verify_workflow_completion(workspace.destination)
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_windows_marker_swap_never_reopens_or_follows_the_marker_path(self) -> None:
        """Regression for #5051: the retained fd survives a Windows-style marker swap."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                external = temporary / "external-marker"
                external.write_text("external content\n", encoding="utf-8")
                original_marker = temporary / "original-marker"
                try:
                    os.replace(workspace.reservation, original_marker)
                    os.symlink(external, workspace.reservation)
                except PermissionError:
                    # Windows denies replacement while the retained descriptor is open.
                    self.assertTrue(workspace.reservation.is_file())
                original_open = complete_client_workflow.os.open

                def reject_marker_reopen(path: Path, flags: int, mode: int = 0o777) -> int:
                    if Path(path) == workspace.reservation:
                        raise AssertionError("the marker path must not be reopened")
                    return original_open(path, flags, mode)

                with mock.patch.object(complete_client_workflow.os, "name", "nt"), mock.patch.object(
                    complete_client_workflow.os, "O_NOFOLLOW", None, create=True
                ), mock.patch.object(complete_client_workflow.os, "open", side_effect=reject_marker_reopen):
                    complete_client_workflow._verify_owned_marker(workspace)
                self.assertEqual(external.read_text(encoding="utf-8"), "external content\n")
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_staging_substitution_is_left_for_manual_inspection(self) -> None:
        """Regression for #5051: cleanup only removes the staging directory this run owns."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            replacement = temporary / "external-stage"
            replacement.mkdir()
            (replacement / "external.txt").write_text("external content\n", encoding="utf-8")
            os.rmdir(workspace.staging)
            os.replace(replacement, workspace.staging)

            with self.assertRaisesRegex(RuntimeError, "staging is no longer owned"):
                complete_client_workflow.release_workflow_workspace(workspace)

            self.assertEqual(
                (workspace.staging / "external.txt").read_text(encoding="utf-8"),
                "external content\n",
            )

    def test_completion_manifest_is_linked_last_and_verifies_success(self) -> None:
        """Consumers require the hash-verified completion manifest, not marker absence."""

        with TemporaryDirectory() as directory:
            temporary = Path(directory)
            workspace = complete_client_workflow.reserve_workflow_workspace(temporary / "output")
            try:
                (workspace.staging / "artifact.txt").write_text("complete\n", encoding="utf-8")
                (workspace.staging / "workflow_summary.json").write_text("{}\n", encoding="utf-8")
                original_link = complete_client_workflow.os.link
                targets: list[Path] = []

                def record_link(source, target):
                    targets.append(Path(target))
                    return original_link(source, target)

                with mock.patch.object(complete_client_workflow.os, "link", side_effect=record_link):
                    complete_client_workflow.publish_workflow_workspace(workspace)

                self.assertEqual(targets[-1].name, complete_client_workflow.COMPLETION_FILENAME)
                self.assertTrue((workspace.destination / "workflow_summary.json").is_file())
                self.assertTrue(workspace.reservation.is_file())
                completion = complete_client_workflow.verify_workflow_completion(workspace.destination)
                self.assertEqual(
                    [record["name"] for record in completion["artifacts"]],
                    ["artifact.txt", "workflow_summary.json"],
                )
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_staging_is_created_on_the_destination_filesystem_for_hard_link_publish(self) -> None:
        """Hard-link publication requires staging and destination to share a device."""

        with TemporaryDirectory() as directory:
            workspace = complete_client_workflow.reserve_workflow_workspace(Path(directory) / "output")
            try:
                self.assertEqual(workspace.staging.stat().st_dev, workspace.destination.stat().st_dev)
            finally:
                complete_client_workflow.release_workflow_workspace(workspace)

    def test_missing_nofollow_fails_closed_on_non_windows_platforms(self) -> None:
        """Do not silently follow a marker when a non-Windows platform lacks O_NOFOLLOW."""

        if complete_client_workflow.os.name == "nt":
            self.skipTest("Windows uses the O_EXCL plus identity-check fallback")
        with mock.patch.object(complete_client_workflow.os, "O_NOFOLLOW", None):
            with self.assertRaisesRegex(RuntimeError, "cannot open workflow markers"):
                complete_client_workflow._marker_open_flags(writable=True)

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
