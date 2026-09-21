# Survey workflow

## Supported CSV-to-IFC handoff

The supported command is:

```bash
python experiments/prototypes/complete_client_workflow.py input.csv \
  --output-dir /safe/output/run
```

Omitting `--output-dir` publishes to a new temporary directory. An explicit
`--output-dir` must not already exist. The command rejects the repository's
tracked `data/processed` and `data/output` directories. It claims the requested
directory with an atomic create before staging, writes every artifact to a
private sibling staging directory, then promotes complete files without
replacement. `workflow_summary.json` is promoted last and is the ready marker
for consumers. Portable Python has no no-replace whole-directory rename, so
the directory name is reserved while the work runs rather than appearing only
at completion. A failed run removes its empty reservation and private staging;
it never deletes data it cannot prove it created.

The input layout is semicolon-delimited:

```text
localId;y;x;z;code;description
```

For the current client layout, the input is already projected. The workflow
creates a local origin from the data bounds, writes local X/Y/Z coordinates,
and records that origin in JSON. It then creates an IFC 4x3 file with one
`IfcAnnotation` per point. Each `SurveyData` property set contains point ID,
code, description, local coordinates, and reconstructed projected coordinates.

The command's default CRS declaration is SWEREF99 TM (EPSG:3006). Confirm that
it matches the survey before using the output; this software does not infer a
CRS from coordinates.

## LandXML terrain handoff

The CSV-to-IFC result contains survey points, not an engineered terrain. It is
therefore not automatically converted to LandXML. A terrain LandXML can be
created only from a separately authored IFC terrain:

```bash
benny-ifc-to-landxml authored-terrain.ifc terrain.xml \
  --terrain-global-id <IfcGeographicElement-GlobalId>
```

The selected product must be an `IfcGeographicElement` containing exactly one
`IfcTriangulatedFaceSet`, with explicit project length units, map conversion,
target CRS name, and map unit. The exporter preserves authored topology and
does not generate a Delaunay surface, scan unrelated IFC points, or guess CRS
or unit metadata. Its output is N/E/Z and declares metres. Details are in
[IFC terrain to LandXML](IFC_TERRAIN_TO_LANDXML.md).

## Validation boundaries

The test suite checks synthetic point correspondence from CSV through IFC,
plus the terrain producer's serialized XML, constrained LandXML shape, CRS
name, metre units, N/E/Z ordering, and face references. It is not a survey
accuracy assessment and does not establish machine-control, TBC, Civil 3D,
Bonsai, or other application compatibility. Review every deliverable in the
target system and under the project's survey-control process.

## Data handling

Do not use client-labelled repository files as public fixtures, and do not
copy them into ifc-lite. The CC0 `fixtures/ifc-lite-control` set is a separate
synthetic control set for automated checks only.
