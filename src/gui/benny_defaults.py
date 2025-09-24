"""Central location for Benny-specific default settings."""

from __future__ import annotations

DEFAULT_COORDINATE_SYSTEM = {
    "target_crs": {
        "epsg": 3006,
        "name": "SWEREF99 TM",
        "description": "Swedish national coordinate reference system",
    }
}

DEFAULT_LOCAL_ORIGIN = {
    "x": 157_896.160819918,
    "y": 6_407_066.260259042,
    "z": 18.83307838439941,
}


