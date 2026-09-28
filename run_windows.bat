@echo off
setlocal
cd /d "%~dp0"
if exist "..\.python-runtime\python.exe" (
    "..\.python-runtime\python.exe" app.py
    if errorlevel 1 goto failed
    goto finished
)
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -m venv .venv
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python was not found. Install Python 3.10 or newer and enable Add Python to PATH, then run this launcher again.
        goto failed
    )
    python -m venv .venv
)
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" app.py
if errorlevel 1 goto failed
:finished
echo.
echo Finished. Check the output folder for your Excel file.
pause
exit /b 0
:failed
echo.
echo Could not finish. Read the error above. Python 3.10 or newer is required.
pause
exit /b 1

