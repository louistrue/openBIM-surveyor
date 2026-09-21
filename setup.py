"""Setup script for bonsai-topo package"""

from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="bonsai-topo",
    version="1.0.0",
    description="Experimental CSV survey-point to IFC handoff",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Survey Team",
    author_email="",
    url="https://github.com/your-username/bonsai-topo",
    license="AGPL-3.0-or-later",
    license_files=["LICENSE"],
    # Source modules import from the explicit ``src`` package. Discovering from
    # the repository root keeps that package path intact in built wheels.
    packages=find_packages(include=["src", "src.*"]),
    python_requires=">=3.9",
    install_requires=[
        "ifcopenshell>=0.7.0",
        "pandas>=1.3.0",
    ],
    extras_require={
        "gui": ["PyQt6>=6.0.0"],
        "dev": [
            "pytest>=6.0",
            "black>=21.0",
            "flake8>=3.9",
            "mypy>=0.9",
        ],
        "packaging": [
            "pyinstaller>=4.10",
        ],
    },
    entry_points={
        "console_scripts": [
            "benny-csv-to-ifc=src.gui.csv_to_ifc_app:main",
            "benny-ifc-to-landxml=src.core.converters.ifc_to_landxml:main",
            "benny-ifc-to-landxml-gui=src.gui.ifc_to_landxml_app:main",
            "benny-launcher=src.gui.main_launcher:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Scientific/Engineering :: GIS",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
