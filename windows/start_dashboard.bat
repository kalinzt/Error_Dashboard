@echo off
set PROJECT_DIR=%~dp0..
cd /d "%PROJECT_DIR%"
call venv\Scripts\activate.bat
start /B pythonw -m flask --app app run --host=0.0.0.0 --port=8765
