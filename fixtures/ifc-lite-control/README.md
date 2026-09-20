# ifc-lite federation control set

This directory is an intentionally synthetic interoperability fixture. It contains no
customer, field, or project data. The same five surveyed control points are encoded as:

- `terrain.ifc`: IFC 4.3 terrain in a local engineering frame with an
  `IfcMapConversion` to EPSG:3006.
- `terrain.xml`: LandXML 1.2 TIN in absolute EPSG:3006 coordinates.
- `survey.xyz`: an ASCII point cloud in the same absolute coordinates.
- `control.json`: independently stated correspondences and tolerances for automated
  federation checks.

The non-coplanar centre point and asymmetric corner elevations make axis swaps,
unit mistakes, double georeferencing, and mirrored frames observable. This fixture
demonstrates the open Bonsai/IFC → LandXML → point-cloud coordination workflow; it
does not certify any proprietary producer export.

## License

To the extent copyright applies, these four synthetic fixture files are dedicated to
the public domain under CC0 1.0. See `LICENSE-CC0.txt`. The surrounding application
source remains AGPL-3.0-only.

