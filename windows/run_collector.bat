@echo off
cd /d "%~dp0.."
venv\Scripts\python.exe -X utf8 collector.py >> "logs\collector.log" 2>&1
