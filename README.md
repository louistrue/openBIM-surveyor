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
time without replacement, with `workflow_summary.json` last as the ready
marker. This is deliberately not described as an atomic whole-directory rename:
portable Python has no no-replace directory-rename primitive. A failed run
removes its empty reservation and private staging; it never removes data it
cannot prove it created. The summary records the local origin and declared CRS.
The IFC uses metre project and map units and carries local and reconstructed
projected coordinates in its `SurveyData` property sets.

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
