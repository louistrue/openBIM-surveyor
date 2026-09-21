#!/usr/bin/env python3
"""Create an auditable CSV-to-IFC survey handoff.

This entry point intentionally stops before inventing a terrain surface. A
survey CSV produces survey-point annotations in IFC. LandXML is available only
when the caller separately supplies an IFC with an authored terrain TIN and
explicitly identifies that terrain's GlobalId.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import stat
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


@dataclass
class WorkflowWorkspace:
    """A private staging directory and exclusive reservation for one run."""

    destination: Path
    staging: Path
    staging_identity: tuple[int, int]
    reservation: Path
    reservation_identity: tuple[int, int]
    reservation_token: str
    reservation_descriptor: int
    published: bool = False


@dataclass(frozen=True)
class TrustedStagedArtifact:
    """A staged regular file held open while its published link is verified."""

    path: Path
    name: str
    descriptor: int
    identity: tuple[int, int]
    size: int
    sha256: str


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
        # ``mkdtemp`` gives the next reservation attempt a collision-free name.
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


INCOMPLETE_FILENAME = ".bonsai-topo-workflow-incomplete"
COMPLETION_FILENAME = ".complete.json"


def _identity(stat_result: os.stat_result) -> tuple[int, int]:
    """Return the filesystem identity used to bind a marker to this run."""

    return stat_result.st_dev, stat_result.st_ino


def _marker_open_flags(*, writable: bool) -> int:
    """Return flags that never follow a marker symlink where the OS supports it.

    Windows does not expose ``O_NOFOLLOW`` in Python. Its ``O_CREAT | O_EXCL``
    create is the safe fallback used here: an existing final path, including a
    reparse point, is rejected rather than opened. The post-create ``lstat`` /
    descriptor identity check below fails closed if that assumption is not met.
    Other platforms without ``O_NOFOLLOW`` are rejected rather than risking a
    marker write through a symlink.
    """

    flags = (os.O_WRONLY if writable else os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)) | getattr(
        os, "O_BINARY", 0
    )
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is not None:
        return flags | no_follow
    if os.name == "nt":
        return flags
    raise RuntimeError("This platform cannot open workflow markers without following symlinks.")


def _read_file_flags() -> int:
    """Return no-follow read flags, or the Windows identity-check fallback."""

    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is not None:
        return flags | no_follow
    if os.name == "nt":
        return flags
    raise RuntimeError("This platform cannot read workflow files without following symlinks.")


def _create_owned_marker(marker: Path, token: str) -> tuple[int, tuple[int, int]]:
    """Create an incomplete marker and retain its original descriptor for this run."""

    flags = _marker_open_flags(writable=True) | os.O_CREAT | os.O_EXCL
    descriptor = os.open(marker, flags, 0o600)
    try:
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_stat.st_mode):
            raise RuntimeError("Workflow marker is not a regular file.")
        payload = f"token={token}\nstate=incomplete\n".encode("ascii")
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise OSError("Could not write workflow marker.")
            written += count
        os.fsync(descriptor)
        identity = _identity(descriptor_stat)
        marker_stat = os.lstat(marker)
        if not stat.S_ISREG(marker_stat.st_mode) or _identity(marker_stat) != identity:
            raise RuntimeError("Workflow marker ownership could not be verified after creation.")
        return descriptor, identity
    except BaseException:
        os.close(descriptor)
        raise


def _verify_owned_marker(workspace: WorkflowWorkspace) -> None:
    """Verify the originally-created marker descriptor without reopening its path."""

    try:
        descriptor_stat = os.fstat(workspace.reservation_descriptor)
        if _identity(descriptor_stat) != workspace.reservation_identity:
            raise RuntimeError(f"Workflow destination is no longer owned by this run: {workspace.destination}")
        if not stat.S_ISREG(descriptor_stat.st_mode):
            raise RuntimeError(f"Workflow reservation descriptor is not regular: {workspace.destination}")
    except OSError as exc:
        raise RuntimeError(f"Workflow destination is no longer owned by this run: {workspace.destination}") from exc


def _verify_owned_staging(workspace: WorkflowWorkspace) -> None:
    """Reject a substituted staging directory before touching one of its paths."""

    staging_stat = os.lstat(workspace.staging)
    if not stat.S_ISDIR(staging_stat.st_mode) or _identity(staging_stat) != workspace.staging_identity:
        raise RuntimeError("Workflow staging is no longer owned by this run; it was left untouched.")


def _hash_descriptor(descriptor: int) -> str:
    """Return a SHA-256 digest from the beginning of an already-open file."""

    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    while True:
        chunk = os.read(descriptor, 1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def _open_trusted_staged_artifact(workspace: WorkflowWorkspace, artifact: Path) -> TrustedStagedArtifact:
    """Open and hash one unmodified regular staged file without following links."""

    _verify_owned_staging(workspace)
    source_stat = os.lstat(artifact)
    if not stat.S_ISREG(source_stat.st_mode):
        raise RuntimeError(f"Workflow staging contains an unsafe artifact: {artifact}")
    descriptor = os.open(artifact, _read_file_flags())
    try:
        descriptor_stat = os.fstat(descriptor)
        identity = _identity(descriptor_stat)
        if not stat.S_ISREG(descriptor_stat.st_mode) or identity != _identity(source_stat):
            raise RuntimeError(f"Workflow staged artifact changed while opening: {artifact}")
        digest = _hash_descriptor(descriptor)
        if descriptor_stat.st_size != os.lseek(descriptor, 0, os.SEEK_END):
            raise RuntimeError(f"Workflow staged artifact changed while hashing: {artifact}")
        _verify_owned_staging(workspace)
        current_stat = os.lstat(artifact)
        if not stat.S_ISREG(current_stat.st_mode) or _identity(current_stat) != identity:
            raise RuntimeError(f"Workflow staged artifact changed while hashing: {artifact}")
        return TrustedStagedArtifact(
            artifact, artifact.name, descriptor, identity, descriptor_stat.st_size, digest
        )
    except BaseException:
        os.close(descriptor)
        raise


def _hash_destination_against_source(destination: Path, source: TrustedStagedArtifact) -> None:
    """Require the no-replace destination link to match the still-open source exactly."""

    destination_stat = os.lstat(destination)
    if not stat.S_ISREG(destination_stat.st_mode) or _identity(destination_stat) != source.identity:
        raise RuntimeError(f"Published artifact does not match its trusted staged source: {destination}")
    if destination_stat.st_size != source.size:
        raise RuntimeError(f"Published artifact size does not match its trusted staged source: {destination}")
    descriptor = os.open(destination, _read_file_flags())
    try:
        descriptor_stat = os.fstat(descriptor)
        if _identity(descriptor_stat) != source.identity or descriptor_stat.st_size != source.size:
            raise RuntimeError(f"Published artifact changed while verifying: {destination}")
        if _hash_descriptor(descriptor) != source.sha256:
            raise RuntimeError(f"Published artifact hash does not match its trusted staged source: {destination}")
        current_stat = os.lstat(destination)
        if not stat.S_ISREG(current_stat.st_mode) or _identity(current_stat) != source.identity:
            raise RuntimeError(f"Published artifact changed while verifying: {destination}")
    finally:
        os.close(descriptor)


def _read_verified_regular_file(path: Path) -> bytes:
    """Read one regular path, rejecting a link or a detected replacement race."""

    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"Workflow completion references an unsafe artifact: {path}")
    descriptor = os.open(path, _read_file_flags())
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
            raise RuntimeError(f"Workflow artifact changed while opening: {path}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.lstat(path)
        if not stat.S_ISREG(after.st_mode) or _identity(after) != _identity(opened):
            raise RuntimeError(f"Workflow artifact changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def verify_workflow_completion(destination: Path) -> dict[str, object]:
    """Verify the positive ready condition for a published workflow directory.

    A destination is ready only when this function accepts its last-published
    completion manifest and every listed artifact's size and SHA-256 digest.
    The retained incomplete marker is provenance, not a readiness signal.
    """

    destination = destination.resolve()
    completion_path = destination / COMPLETION_FILENAME
    try:
        completion = json.loads(_read_verified_regular_file(completion_path).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Workflow completion manifest is invalid: {completion_path}") from exc
    if not isinstance(completion, dict) or completion.get("format") != "bonsai-topo-workflow-completion-v1":
        raise RuntimeError(f"Workflow completion manifest has an unsupported format: {completion_path}")
    token = completion.get("reservation_token")
    records = completion.get("artifacts")
    if not isinstance(token, str) or len(token) != 64 or not isinstance(records, list) or not records:
        raise RuntimeError(f"Workflow completion manifest is incomplete: {completion_path}")

    names: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise RuntimeError(f"Workflow completion manifest has an invalid artifact record: {completion_path}")
        name = record.get("name")
        expected_hash = record.get("sha256")
        expected_size = record.get("size")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or name in {"", ".", "..", COMPLETION_FILENAME, INCOMPLETE_FILENAME}
            or name in names
            or not isinstance(expected_hash, str)
            or len(expected_hash) != 64
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise RuntimeError(f"Workflow completion manifest has an invalid artifact record: {completion_path}")
        names.add(name)
        payload = _read_verified_regular_file(destination / name)
        if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise RuntimeError(f"Workflow artifact fails completion verification: {destination / name}")
    return completion


def _verify_completion_records(destination: Path, records: list[dict[str, object]]) -> None:
    """Fail before readiness if a previously linked artifact was replaced."""

    for record in records:
        name = record["name"]
        expected_hash = record["sha256"]
        expected_size = record["size"]
        if not isinstance(name, str) or not isinstance(expected_hash, str) or not isinstance(expected_size, int):
            raise RuntimeError("Workflow has an invalid internal completion record.")
        payload = _read_verified_regular_file(destination / name)
        if len(payload) != expected_size or hashlib.sha256(payload).hexdigest() != expected_hash:
            raise RuntimeError(f"Published artifact changed before completion: {destination / name}")


def reserve_workflow_workspace(destination: Path) -> WorkflowWorkspace:
    """Atomically claim a new destination and create a private sibling stage.

    Creating the destination itself is the portable no-replace operation. A
    separate lock beside a not-yet-created destination leaves a check/rename
    window in which another caller can create that destination.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as exc:
        raise FileExistsError(
            f"Refusing to overwrite existing workflow output directory: {destination}"
        ) from exc
    reservation = destination / INCOMPLETE_FILENAME
    token = secrets.token_hex(32)

    try:
        reservation_descriptor, identity = _create_owned_marker(reservation, token)
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{destination.name}.bonsai-topo-stage-",
                dir=destination.parent,
            )
        )
        staging_stat = os.lstat(staging)
        if not stat.S_ISDIR(staging_stat.st_mode):
            raise RuntimeError("Workflow staging is not a private directory.")
        staging_identity = _identity(staging_stat)
    except BaseException:
        if "reservation_descriptor" in locals():
            os.close(reservation_descriptor)
        # The destination is an explicit incomplete handoff. Never remove it:
        # another process may have placed evidence there after reservation.
        raise
    return WorkflowWorkspace(
        destination,
        staging,
        staging_identity,
        reservation,
        identity,
        token,
        reservation_descriptor,
    )


def release_workflow_workspace(workspace: WorkflowWorkspace) -> None:
    """Remove private staging only; incomplete destinations require inspection."""

    try:
        try:
            _verify_owned_staging(workspace)
        except FileNotFoundError:
            return
        shutil.rmtree(workspace.staging)
    finally:
        os.close(workspace.reservation_descriptor)


def publish_workflow_workspace(workspace: WorkflowWorkspace) -> None:
    """Publish staged files without replacing a destination or an artifact.

    There is no cross-platform directory equivalent of ``rename(...,
    NOREPLACE)``. The destination directory was atomically reserved before
    work began, and each same-filesystem staged artifact is linked into it with
    ``os.link`` (which fails if the target already exists). A hash manifest is
    linked last, so its verified presence is the ready condition for consumers.
    """

    _verify_owned_marker(workspace)

    _verify_owned_staging(workspace)
    staged_artifacts = list(workspace.staging.iterdir())
    if not staged_artifacts:
        raise RuntimeError("Workflow staging directory contains no artifacts.")
    if not (workspace.staging / "workflow_summary.json").is_file():
        raise RuntimeError("Workflow staging is missing its required ready-marker summary.")
    if any(artifact.name == COMPLETION_FILENAME for artifact in staged_artifacts):
        raise RuntimeError(f"Workflow staging must not pre-create {COMPLETION_FILENAME}.")

    records: list[dict[str, object]] = []
    for artifact in sorted(staged_artifacts, key=lambda candidate: candidate.name):
        trusted = _open_trusted_staged_artifact(workspace, artifact)
        try:
            _verify_owned_staging(workspace)
            current_stat = os.lstat(trusted.path)
            if not stat.S_ISREG(current_stat.st_mode) or _identity(current_stat) != trusted.identity:
                raise RuntimeError(f"Workflow staged artifact changed before publication: {trusted.path}")
            target = workspace.destination / trusted.name
            os.link(trusted.path, target)
            _hash_destination_against_source(target, trusted)
            records.append({"name": trusted.name, "sha256": trusted.sha256, "size": trusted.size})
        finally:
            os.close(trusted.descriptor)

    _verify_owned_staging(workspace)
    _verify_completion_records(workspace.destination, records)
    completion_staging = workspace.staging / COMPLETION_FILENAME
    completion = {
        "format": "bonsai-topo-workflow-completion-v1",
        "reservation_token": workspace.reservation_token,
        "artifacts": records,
    }
    completion_bytes = (json.dumps(completion, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(
        completion_staging,
        _marker_open_flags(writable=True) | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        written = 0
        while written < len(completion_bytes):
            count = os.write(descriptor, completion_bytes[written:])
            if count <= 0:
                raise OSError("Could not write workflow completion manifest.")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)

    trusted_completion = _open_trusted_staged_artifact(workspace, completion_staging)
    try:
        _verify_owned_staging(workspace)
        current_stat = os.lstat(trusted_completion.path)
        if not stat.S_ISREG(current_stat.st_mode) or _identity(current_stat) != trusted_completion.identity:
            raise RuntimeError("Workflow completion manifest changed before publication.")
        os.link(trusted_completion.path, workspace.destination / COMPLETION_FILENAME)
        _hash_destination_against_source(workspace.destination / COMPLETION_FILENAME, trusted_completion)
    finally:
        os.close(trusted_completion.descriptor)
    _verify_owned_marker(workspace)
    workspace.published = True


def workflow_output_paths(output_dir: Path, stem: str, include_landxml: bool) -> dict[str, Path]:
    """Return the public paths that a successfully published run will contain."""

    outputs = {
        "processed_csv": output_dir / f"{stem}_processed.csv",
        "transform_info": output_dir / f"{stem}_processed_transform_info.json",
        "ifc": output_dir / f"{stem}_survey_points.ifc",
        "summary": output_dir / "workflow_summary.json",
        "completion_manifest": output_dir / COMPLETION_FILENAME,
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
