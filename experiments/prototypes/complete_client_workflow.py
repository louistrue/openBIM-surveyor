#!/usr/bin/env python3
"""Create an auditable CSV-to-IFC survey handoff.

This entry point intentionally stops before inventing a terrain surface. A
survey CSV produces survey-point annotations in IFC. LandXML is available only
when the caller separately supplies an IFC with an authored terrain TIN and
explicitly identifies that terrain's GlobalId.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))
WORKFLOW_DIRECTORY = Path(__file__).resolve().parent
if str(WORKFLOW_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(WORKFLOW_DIRECTORY))

from src.core.converters.csv_to_ifc import create_basic_ifc_with_survey_points
from src.core.converters.ifc_to_landxml import (
    LandXmlExportError,
    export_ifc_terrain_to_landxml,
)


TRACKED_OUTPUT_DIRECTORIES = (
    REPOSITORY_ROOT / "data" / "processed",
    REPOSITORY_ROOT / "data" / "output",
)


@dataclass(frozen=True)
class WorkflowWorkspace:
    """A private staging directory and exclusive reservation for one run."""

    destination: Path
    staging: Path
    reservation: Path


def default_config() -> dict[str, Any]:
    """Return the CRS declaration required for this client's projected CSV."""

    return {
        "source_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "target_crs": {"epsg": 3006, "name": "SWEREF99 TM"},
        "local_origin": {"x": 0, "y": 0, "z": 0},
        "precision": {"decimal_places": 3},
    }


def resolve_output_directory(requested: Path | None) -> Path:
    """Choose an as-yet-unpublished directory outside tracked sample outputs."""

    if requested is None:
        # ``mkdtemp`` reserves a collision-free name. Remove its empty directory
        # immediately: publication below is one atomic directory rename.
        output_dir = Path(tempfile.mkdtemp(prefix="bonsai-topo-workflow-"))
        output_dir.rmdir()
        return output_dir

    output_dir = requested.resolve()
    for tracked_directory in TRACKED_OUTPUT_DIRECTORIES:
        try:
            output_dir.relative_to(tracked_directory)
        except ValueError:
            continue
        raise ValueError(
            f"Refusing to write to tracked output directory: {output_dir}. "
            "Choose a directory outside data/processed and data/output."
        )
    return output_dir


def _path_is_occupied(path: Path) -> bool:
    """Include a dangling symlink, which ``Path.exists`` intentionally omits."""

    return path.exists() or path.is_symlink()


def _reservation_path(destination: Path) -> Path:
    return destination.parent / f".{destination.name}.bonsai-topo-reservation"


def reserve_workflow_workspace(destination: Path) -> WorkflowWorkspace:
    """Exclusively reserve a destination and create a private sibling staging dir."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    reservation = _reservation_path(destination)
    try:
        descriptor = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Another workflow is already preparing this output directory: {destination}."
        ) from exc
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(f"pid={os.getpid()}\n")

    try:
        if _path_is_occupied(destination):
            raise FileExistsError(
                f"Refusing to overwrite existing workflow output directory: {destination}"
            )
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.bonsai-topo-stage-",
                dir=destination.parent,
            )
        )
    except BaseException:
        reservation.unlink(missing_ok=True)
        raise
    return WorkflowWorkspace(destination, staging, reservation)


def release_workflow_workspace(workspace: WorkflowWorkspace) -> None:
    """Remove only this run's private staging directory and reservation."""

    if workspace.staging.exists():
        shutil.rmtree(workspace.staging)
    workspace.reservation.unlink(missing_ok=True)


def publish_workflow_workspace(workspace: WorkflowWorkspace) -> None:
    """Atomically publish a completed run without replacing an existing output."""

    if _path_is_occupied(workspace.destination):
        raise FileExistsError(
            f"Refusing to overwrite existing workflow output directory: {workspace.destination}"
        )
    os.replace(workspace.staging, workspace.destination)


def workflow_output_paths(output_dir: Path, stem: str, include_landxml: bool) -> dict[str, Path]:
    """Return the public paths that a successfully published run will contain."""

    outputs = {
        "processed_csv": output_dir / f"{stem}_processed.csv",
        "transform_info": output_dir / f"{stem}_processed_transform_info.json",
        "ifc": output_dir / f"{stem}_survey_points.ifc",
        "summary": output_dir / "workflow_summary.json",
    }
    if include_landxml:
        outputs["landxml"] = output_dir / f"{stem}_terrain.xml"
    return outputs


def run_workflow(
    input_csv: Path,
    output_dir: Path,
    *,
    terrain_ifc: Path | None = None,
    terrain_global_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process one client-format CSV and optionally export an authored terrain.

    The input uses the client export's ``localId;y;x;z;code;description``
    columns. Processing creates local coordinates and a transform record; IFC
    annotations retain both local and projected coordinates. A points-only IFC
    is deliberately not passed to the LandXML producer.
    """

    output_dir = resolve_output_directory(output_dir)
    input_csv = input_csv.resolve()
    if not input_csv.is_file():
        raise FileNotFoundError(f"Survey CSV does not exist or is not a file: {input_csv}")
    if (terrain_ifc is None) != (terrain_global_id is None):
        raise ValueError("--terrain-ifc and --terrain-global-id must be supplied together.")

    active_config = config or default_config()
    workspace = reserve_workflow_workspace(output_dir)
    public_outputs = workflow_output_paths(
        output_dir, input_csv.stem, include_landxml=terrain_ifc is not None
    )
    staged_outputs = workflow_output_paths(
        workspace.staging, input_csv.stem, include_landxml=terrain_ifc is not None
    )
    try:
        from client_data_processor import process_client_csv

        if not process_client_csv(input_csv, staged_outputs["processed_csv"], active_config):
            raise RuntimeError("CSV processing failed; see the diagnostic above.")

        transform_info = json.loads(staged_outputs["transform_info"].read_text(encoding="utf-8"))
        transform_info["target_crs"] = active_config["target_crs"]
        staged_outputs["transform_info"].write_text(
            json.dumps(transform_info, indent=2) + "\n", encoding="utf-8"
        )
        if not create_basic_ifc_with_survey_points(
            staged_outputs["processed_csv"], staged_outputs["ifc"], transform_info
        ):
            raise RuntimeError("IFC export failed; install a compatible ifcopenshell package.")

        landxml_status: dict[str, str] = {
            "status": "not_requested",
            "reason": (
                "Survey-point IFCs are not terrain TINs. Author and validate an "
                "IfcGeographicElement with one IfcTriangulatedFaceSet before exporting LandXML."
            ),
        }
        if terrain_ifc is not None:
            try:
                mesh = export_ifc_terrain_to_landxml(
                    terrain_ifc,
                    staged_outputs["landxml"],
                    terrain_global_id=terrain_global_id,
                )
            except LandXmlExportError as exc:
                raise RuntimeError(f"LandXML export rejected the authored terrain: {exc}") from exc
            landxml_status = {
                "status": "created",
                "path": str(public_outputs["landxml"]),
                "terrain": mesh.name,
                "points": str(len(mesh.vertices_enz)),
                "faces": str(len(mesh.faces)),
                "crs": mesh.crs_name,
            }

        summary: dict[str, Any] = {
            "workflow": "CSV survey points to IFC annotations",
            "input": str(input_csv),
            "outputs": {name: str(path) for name, path in public_outputs.items()},
            "crs": active_config["target_crs"],
            "landxml": landxml_status,
            "limitations": [
                "The generated IFC contains survey-point annotations, not a terrain design.",
                "No machine-control or third-party application compatibility is certified.",
            ],
        }
        staged_outputs["summary"].write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        publish_workflow_workspace(workspace)
        return summary
    finally:
        release_workflow_workspace(workspace)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_csv", type=Path, help="client-format survey CSV")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="new directory outside tracked data/ outputs (default: a new temporary directory)",
    )
    parser.add_argument(
        "--terrain-ifc",
        type=Path,
        help="separate IFC containing an authored IfcGeographicElement terrain TIN",
    )
    parser.add_argument(
        "--terrain-global-id",
        help="required GlobalId of the authored IfcGeographicElement terrain",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        output_dir = resolve_output_directory(args.output_dir)
        summary = run_workflow(
            args.input_csv,
            output_dir,
            terrain_ifc=args.terrain_ifc,
            terrain_global_id=args.terrain_global_id,
        )
    except (FileExistsError, FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        print(f"Workflow failed: {exc}", file=sys.stderr)
        return 1

    print(f"Workflow outputs: {output_dir}")
    print(f"Survey-point IFC: {summary['outputs']['ifc']}")
    if summary["landxml"]["status"] == "created":
        print(f"Authored-terrain LandXML: {summary['landxml']['path']}")
    else:
        print("LandXML was not produced: author a terrain TIN first (see workflow_summary.json).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
