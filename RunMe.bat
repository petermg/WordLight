@echo off
REM Check if python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python not found! Downloading portable Python...
    curl -LO https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip
    powershell -Command "Expand-Archive python-3.12.3-embed-amd64.zip -DestinationPath portablepython"
    set PYTHON_EXE=%cd%\portablepython\python.exe
) else (
    set PYTHON_EXE=python
)

REM Create virtual environment if not exists
if not exist venv (
    %PYTHON_EXE% -m venv venv
)

REM Activate venv
call venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install requirements
python -m pip install -r requirements.txt

REM Run the script
python WordLight.py

pause
