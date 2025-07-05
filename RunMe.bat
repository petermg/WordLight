@echo off

REM Download with curl if available, else use PowerShell
where curl >nul 2>nul
IF %ERRORLEVEL%==0 (
    IF NOT EXIST WordLight.py (
        echo Downloading WordLight.py using curl...
        curl -L -o WordLight.py https://raw.githubusercontent.com/petermg/WordLight/main/WordLight.py
    ) ELSE (
        echo WordLight.py already exists, skipping download.
    )
    IF NOT EXIST requirements.txt (
        echo Downloading requirements.txt using curl...
        curl -L -o requirements.txt https://raw.githubusercontent.com/petermg/WordLight/main/requirements.txt
    ) ELSE (
        echo requirements.txt already exists, skipping download.
    )
) ELSE (
    IF NOT EXIST WordLight.py (
        echo Downloading WordLight.py using PowerShell...
        powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/petermg/WordLight/refs/heads/main/WordLight.py -OutFile 'WordLight.py'"
    ) ELSE (
        echo WordLight.py already exists, skipping download.
    )
    IF NOT EXIST requirements.txt (
        echo Downloading requirements.txt using PowerShell...
        powershell -Command "Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/petermg/WordLight/refs/heads/main/requirements.txt' -OutFile 'requirements.txt'"
    ) ELSE (
        echo requirements.txt already exists, skipping download.
    )
)

REM Check if python is installed
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python not found! Downloading portable Python...

    REM -- Check if curl exists --
    where curl >nul 2>nul
    if %errorlevel%==0 (
        REM -- Use curl to download --
        curl -LO https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip
    ) else (
        REM -- Fallback to PowerShell to download --
        powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.3/python-3.12.3-embed-amd64.zip' -OutFile 'python-3.12.3-embed-amd64.zip'"
    )

    REM -- Use PowerShell to extract, since it's always present --
    powershell -Command "Expand-Archive 'python-3.12.3-embed-amd64.zip' -DestinationPath 'portablepython'"

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
python -m pip install --no-deps -r requirements.txt

REM Run the script
python WordLight.py

pause
