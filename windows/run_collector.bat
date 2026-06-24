@echo off
set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"
call venv\Scripts\activate.bat
python collector.py >> "%PROJECT_DIR%\logs\collector.log" 2>&1
