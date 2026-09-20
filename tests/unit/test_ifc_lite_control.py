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
        self.control = json.loads((FIXTURE / "control.json").read_text(encoding="utf-8"))

    def test_fixture_is_explicitly_synthetic_and_rights_clear(self):
        self.assertTrue(self.control["synthetic"])
        self.assertFalse(self.control["customerData"])
        self.assertEqual(self.control["license"], "CC0-1.0")
        self.assertTrue((FIXTURE / "LICENSE-CC0.txt").is_file())

    def test_landxml_and_xyz_match_independent_projected_controls(self):
        expected = {row["id"]: row["projected"] for row in self.control["points"]}
        root = ET.parse(FIXTURE / "terrain.xml").getroot()
        landxml = {}
        for point in root.findall(".//lx:CgPoint", NS):
            northing, easting, elevation = map(float, point.text.split())
            landxml[point.attrib["name"]] = [easting, northing, elevation]
        self.assertEqual(landxml, expected)

        xyz = [list(map(float, line.split()[:3])) for line in
               (FIXTURE / "survey.xyz").read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(xyz, list(expected.values()))

    def test_ifc_local_mesh_plus_map_origin_matches_projected_controls(self):
        text = (FIXTURE / "terrain.ifc").read_text(encoding="utf-8")
        conversion = re.search(r"IFCMAPCONVERSION\([^,]+,[^,]+,([^,]+),([^,]+),([^,]+),", text)
        point_list = re.search(r"IFCCARTESIANPOINTLIST3D\(\(\((.*?)\)\)\);", text)
        self.assertIsNotNone(conversion)
        self.assertIsNotNone(point_list)
        origin = list(map(float, conversion.groups()))
        local = [list(map(float, row.split(","))) for row in point_list.group(1).split("),(")]
        projected = [[point[i] + origin[i] for i in range(3)] for point in local]
        self.assertEqual(projected, [row["projected"] for row in self.control["points"]])


if __name__ == "__main__":
    unittest.main()
