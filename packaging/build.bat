@echo off
REM Build script for Benny's survey tools
REM Requires Python 3.11+ and virtual environment

echo Building Benny Survey Tools...
echo ================================

REM Check if virtual environment exists
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

echo.
echo Installing CSV to IFC dependencies...
pip install -r packaging\requirements\csv-to-ifc.txt
pip install pyinstaller

echo.
echo Building CSV to IFC executable...
pyinstaller --noconfirm --clean --additional-hooks-dir packaging\hooks packaging\specs\csv_to_ifc.spec

echo.
echo Installing IFC to LandXML dependencies...
pip install -r packaging\requirements\ifc-to-landxml.txt

echo.
echo Building IFC to LandXML executable...
pyinstaller --noconfirm --clean --additional-hooks-dir packaging\hooks packaging\specs\ifc_to_landxml.spec

echo.
echo Build complete!
echo Executables are in the dist\ folder:
echo - dist\Benny CSV to IFC\Benny CSV to IFC.exe
echo - dist\Benny IFC to LandXML\Benny IFC to LandXML.exe
echo.
pause
