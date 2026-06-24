@echo off
cd /d "%~dp0.."
start /B venv\Scripts\pythonw.exe -m flask --app app run --host=0.0.0.0 --port=8765
