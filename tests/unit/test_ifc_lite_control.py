"""Invariant tests for the synthetic ifc-lite federation control set."""

import json
import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


FIXTURE = Path(__file__).parents[2] / "fixtures" / "ifc-lite-control"
NS = {"lx": "http://www.landxml.org/schema/LandXML-1.2"}


class IfcLiteControlFixtureTest(unittest.TestCase):
    def setUp(self):
        """Load the independently stated controls used by every fixture check."""
        self.control = json.loads((FIXTURE / "control.json").read_text(encoding="utf-8"))

    def test_fixture_is_explicitly_synthetic_and_rights_clear(self):
        """Require machine-readable synthetic-data and licensing declarations."""
        self.assertTrue(self.control["synthetic"])
        self.assertFalse(self.control["customerData"])
        self.assertEqual(self.control["license"], "CC0-1.0")
        self.assertTrue((FIXTURE / "LICENSE-CC0.txt").is_file())

    def test_landxml_and_xyz_match_independent_projected_controls(self):
        """Compare both survey formats with the controls at the declared tolerance."""
        tolerance = self.control["toleranceMetres"]
        expected = {row["id"]: row["projected"] for row in self.control["points"]}
        root = ET.parse(FIXTURE / "terrain.xml").getroot()
        landxml = {}
        for point in root.findall(".//lx:CgPoint", NS):
            northing, easting, elevation = map(float, point.text.split())
            landxml[point.attrib["name"]] = [easting, northing, elevation]
        self.assertEqual(list(landxml), list(expected))
        for point_id, expected_coordinate in expected.items():
            with self.subTest(format="LandXML", point=point_id):
                self.assert_coordinates_within(
                    landxml[point_id], expected_coordinate, tolerance
                )

        xyz = [list(map(float, line.split()[:3])) for line in
               (FIXTURE / "survey.xyz").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(xyz), len(expected))
        for point_id, actual, expected_coordinate in zip(
                expected, xyz, expected.values(), strict=True):
            with self.subTest(format="XYZ", point=point_id):
                self.assert_coordinates_within(actual, expected_coordinate, tolerance)

    def test_ifc_local_mesh_plus_map_origin_matches_projected_controls(self):
        """Resolve the IFC map conversion and compare its mesh with the controls."""
        text = (FIXTURE / "terrain.ifc").read_text(encoding="utf-8")
        conversion = re.search(r"IFCMAPCONVERSION\([^,]+,[^,]+,([^,]+),([^,]+),([^,]+),", text)
        point_list = re.search(r"IFCCARTESIANPOINTLIST3D\(\(\((.*?)\)\)\);", text)
        self.assertIsNotNone(conversion)
        self.assertIsNotNone(point_list)
        origin = list(map(float, conversion.groups()))
        local = [list(map(float, row.split(","))) for row in point_list.group(1).split("),(")]
        projected = [[point[i] + origin[i] for i in range(3)] for point in local]
        expected = [row["projected"] for row in self.control["points"]]
        self.assertEqual(len(projected), len(expected))
        for index, (actual, expected_coordinate) in enumerate(
                zip(projected, expected, strict=True)):
            with self.subTest(point=self.control["points"][index]["id"]):
                self.assert_coordinates_within(
                    actual, expected_coordinate, self.control["toleranceMetres"]
                )

    def assert_coordinates_within(self, actual, expected, tolerance):
        """Assert corresponding ordinates differ by no more than tolerance metres."""
        self.assertEqual(len(actual), len(expected))
        for ordinate, (actual_value, expected_value) in enumerate(
                zip(actual, expected, strict=True)):
            with self.subTest(ordinate=ordinate):
                self.assertLessEqual(abs(actual_value - expected_value), tolerance)


if __name__ == "__main__":
    unittest.main()
