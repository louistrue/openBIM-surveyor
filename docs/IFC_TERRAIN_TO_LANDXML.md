# IFC terrain to LandXML

The production exporter is intentionally a terrain-TIN producer, not a generic
IFC geometry converter. It exports one explicitly selected terrain and preserves
the triangulation that was authored in Bonsai.

Run it headlessly:

```bash
benny-ifc-to-landxml model.ifc terrain.xml \
  --terrain-global-id 0J$exampleTerrainGlobalId
```

The GUI calls the same producer and asks for the same GlobalId. The GlobalId is
the IFC GlobalId of the intended `IfcGeographicElement`; it is not the display
name or the numeric STEP id.

## Required IFC contract

The selected product must be an `IfcGeographicElement` with exactly one
`IfcTriangulatedFaceSet` in its product representation. Its `CoordIndex` is
copied directly to LandXML faces. When present, `PnIndex` is resolved before
those faces are written, so the authored coordinate indirection is retained.
Degenerate faces are rejected both before and after serialization. The producer
deliberately does not:

- scan `IfcCartesianPoint` entities;
- treat `IfcSlab`, `IfcBuildingElementProxy`, or any other building product as
  terrain; or
- create a Delaunay triangulation or otherwise repair topology.

The representation context must have exactly one matching `IfcMapConversion`,
with an explicitly named `IfcProjectedCRS` and an explicit `MapUnit`. The IFC
project must also define exactly one length unit. Missing or ambiguous metadata
stops the export with a diagnostic rather than assuming a local CRS, EPSG code,
or metre scale.

`IfcGeometricRepresentationSubContext` representations (for example `Body`)
resolve their map conversion from the `ParentContext`. A non-identity
`WorldCoordinateSystem` on the resolved map context is rejected with an
actionable diagnostic: this P0 producer does not silently risk applying that
transform twice.

## Coordinate contract

The exporter composes the selected product's `IfcLocalPlacement` chain and then
applies the selected context's map conversion once. For local IFC coordinate
`(x, y, z)`, expressed in IFC project units, the conversion is:

```text
E = Eastings + Scale * (XAxisAbscissa * FactorX * x - XAxisOrdinate * FactorY * y)
N = Northings + Scale * (XAxisOrdinate * FactorX * x + XAxisAbscissa * FactorY * y)
Z = OrthogonalHeight + Scale * FactorZ * z
```

`IfcMapConversion.Scale` is the combined local-project-unit to map-unit scale;
it is not multiplied by a separately inferred unit ratio. If project and map
units differ and `Scale` is omitted, export stops rather than guessing it.
`FactorX`, `FactorY`, and `FactorZ` are applied when an
`IfcMapConversionScaled` supplies them; absent factors are one.
The `XAxisAbscissa`/`XAxisOrdinate` map-direction vector is normalized before
use and a zero vector is rejected.

The generated LandXML uses metric metre `Units`, records the supplied IFC target
CRS name, and writes every TIN coordinate as `N E Z` (Northing, Easting,
Elevation). That ordering is intentionally different from IFC's `X Y Z` order.

Before the atomically replaced output file is written, the exact serialized bytes
are parsed and checked for the LandXML 1.2 namespace/version, metric units,
coordinate triples, one selected surface, and valid authored face references.
