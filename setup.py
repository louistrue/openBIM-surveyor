"""Setup script for bonsai-topo package"""

from setuptools import setup, find_packages
from pathlib import Path

this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

setup(
    name="bonsai-topo",
    version="1.0.0",
    description="Open BIM Survey Workflow - Production-ready alternative to Topocad",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Survey Team",
    author_email="",
    url="https://github.com/your-username/bonsai-topo",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.9",
    install_requires=[
        "ifcopenshell>=0.7.0",
        "PyQt6>=6.0.0",
        "numpy>=1.20.0",
        "pandas>=1.3.0",
    ],
    extras_require={
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
            "benny-ifc-to-landxml=src.gui.ifc_to_landxml_app:main",
            "benny-launcher=src.gui.main_launcher:main",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Scientific/Engineering :: GIS",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
