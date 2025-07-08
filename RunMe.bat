@echo off
setlocal

REM =============================
echo 1. Set WinPython version/info
REM =============================
set WINPY_VER=3.10.6.1b1
set WINPY_EXE=Winpython64-3.10.6.1b1.exe
set WINPY_URL=https://github.com/winpython/winpython/releases/download/4.7.20220807/Winpython64-3.10.6.1b1.exe

REM ==== PATH AUTODETECTION BLOCK ====
REM Find a folder with WPy* or WinPython* that contains python.exe in any subdirectory
set "WINPY_DIR="
set "PYTHON_SUBDIR="
for /d %%D in (WPy* WinPython*) do (
    for /d %%S in ("%%D\python-*") do (
        if exist "%%S\python.exe" (
            set "WINPY_DIR=%%D"
            set "PYTHON_SUBDIR=%%~nxS"
        )
    )
)
if not defined WINPY_DIR (
    set WINPY_DIR=WPy64-31061b1
    set PYTHON_SUBDIR=python-3.10.6.amd64
)
echo Found WINPY_DIR=%WINPY_DIR%
echo Found PYTHON_SUBDIR=%PYTHON_SUBDIR%

REM =============================
echo 2. Download WinPython if needed
REM =============================
IF NOT EXIST "%WINPY_EXE%" (
    echo Downloading WinPython %WINPY_VER%...
    curl -L -o "%WINPY_EXE%" "%WINPY_URL%"
)

REM =============================
echo 3. Extract WinPython if needed
REM =============================
IF NOT EXIST "%WINPY_DIR%\%PYTHON_SUBDIR%\python.exe" (
    echo Extracting WinPython...
    "%CD%\%WINPY_EXE%" -y -o"%CD%"
) else (
    echo WinPython already extracted at %WINPY_DIR%\%PYTHON_SUBDIR%
)

REM =============================
echo 4. Set Python paths
REM =============================
set PYTHON_ROOT=%CD%\%WINPY_DIR%\%PYTHON_SUBDIR%
set PYTHON_EXE=%PYTHON_ROOT%\python.exe
set PIP_EXE=%PYTHON_ROOT%\Scripts\pip.exe

REM Update PATH so 'pip'/'python' work in this shell
set PATH=%PYTHON_ROOT%\Scripts;%PYTHON_ROOT%;%PATH%

REM =============================
echo 5. Download project files
REM =============================
IF NOT EXIST WordLight.py (
    curl -L -o WordLight.py https://raw.githubusercontent.com/petermg/WordLight/main/WordLight.py
)
IF NOT EXIST requirements.txt (
    curl -L -o requirements.txt https://raw.githubusercontent.com/petermg/WordLight/main/requirements.txt
)

REM =============================
echo 6. Create virtual environment (optional, but recommended)
REM =============================
IF NOT EXIST venv (
    "%PYTHON_EXE%" -m venv venv
)

REM =============================
echo 7. Activate venv and install requirements
REM =============================
call venv\Scripts\activate.bat
%PYTHON_EXE% -m pip install --upgrade pip
%PYTHON_EXE% -m pip install --no-deps -r requirements.txt

REM =============================
echo 8. Run your script
REM =============================
python WordLight.py

pause
endlocal
