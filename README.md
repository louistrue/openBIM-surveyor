# openBIM Surveyor

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

An experimental, auditable handoff from a client-format survey CSV to IFC
survey-point annotations. It is not a replacement for survey review, terrain
design, machine-control validation, or a proprietary application's export.

## What is reproducible

The supported workflow accepts the semicolon-delimited client layout
`localId;y;x;z;code;description`. It writes a cleaned local-coordinate CSV, a
transform record, an IFC 4x3 file containing `IfcAnnotation` survey points,
and a summary to a new temporary directory by default:

```bash
python -m pip install -r requirements.txt
python experiments/prototypes/complete_client_workflow.py path/to/survey.csv
```

Use an explicit directory when the outputs need to be retained:

```bash
python experiments/prototypes/complete_client_workflow.py path/to/survey.csv \
  --output-dir /safe/output/survey-run
```

The command refuses `data/processed` and `data/output`, so it does not replace
tracked sample outputs. An explicit output directory must be new; the workflow
claims that directory with an atomic create before it starts, then builds its
files in private sibling staging. Completed artifacts are promoted one at a
time without replacement. A final `.complete.json` manifest records the
per-artifact SHA-256 hashes and byte sizes and is promoted last. This is
deliberately not described as an atomic whole-directory rename: portable Python
has no no-replace directory-rename primitive. A destination is ready only when
`.complete.json` is present *and* every artifact it lists matches its recorded
hash and size (use `verify_workflow_completion` when embedding this workflow).
`workflow_summary.json` is an ordinary verified artifact, not a ready marker.
The hidden `.bonsai-topo-workflow-incomplete` marker remains permanently as
reservation provenance and is never removed or used as a negative readiness
signal. On any failure, all destination paths remain for inspection; only the
still-owned private staging directory is removed automatically. This avoids
deleting a path that another process might have substituted. The summary
records the local origin and declared CRS. The IFC uses metre project and map
units and carries local and reconstructed projected coordinates in its
`SurveyData` property sets.

The reservation marker has a per-run random token and is created exclusively
without following symlinks where the platform supports it. Its original file
descriptor remains open for the run, so the workflow never reopens, follows,
removes, or replaces the marker path (including on Windows). Every staged file
is opened without following links where available, hashed while its descriptor
is open, hard-linked without replacement, and compared against that trusted
source before the completion manifest can be published. The final manifest
lets consumers detect later artifact substitution by verifying all hashes.
This is a cooperative-concurrency protocol, not an authenticity boundary
against a same-user principal that can modify the destination directory or its
contents; storage permissions must protect deliverables.

## Terrain LandXML is a separate, explicit handoff

Survey points are not a terrain design. This repository deliberately does not
triangulate loose survey points or arbitrary building geometry into LandXML.
After a qualified operator authors and reviews a terrain as one
`IfcGeographicElement` with one `IfcTriangulatedFaceSet`, export that selected
terrain with its GlobalId:

```bash
benny-ifc-to-landxml authored-terrain.ifc terrain.xml \
  --terrain-global-id <IfcGeographicElement-GlobalId>
```

The producer preserves the authored face list, requires explicit map conversion
and units, writes N/E/Z LandXML coordinates, and validates the serialized XML
and its emitted LandXML subset before replacing the requested file. It does
not certify compatibility with machine-control systems, TBC, Civil 3D, Bonsai,
or any other application. See [the terrain contract](docs/IFC_TERRAIN_TO_LANDXML.md).

## Verification

```bash
python -m unittest discover -s tests
```

The end-to-end CSV-to-IFC test builds its own synthetic survey in a temporary
directory and checks point IDs, metadata, local/projected correspondence, CRS,
and metre units. It is skipped only when `pandas` or `ifcopenshell` is not
installed. Terrain LandXML contract tests use synthetic IFC-shaped objects and
validate XML well-formedness, unit declarations, coordinate ordering, and face
references without using customer data.

## Data and licensing

The synthetic `fixtures/ifc-lite-control` set is CC0 as declared inside that
directory. It is suitable for automated interoperability checks but does not
certify any third-party product.

Client-labelled files already present elsewhere in this repository are not
test fixtures or publication-ready examples. Do not copy them into ifc-lite or
redistribute them without the data owner's documented permission.

The source code is licensed under the GNU Affero General Public License v3.0
or later; see [LICENSE](LICENSE). The package metadata uses the same license.
