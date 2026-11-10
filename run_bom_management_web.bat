@echo off
rem BOM Management - web tool local. Chay file nay hoac BOM_MANAGEMENT.vbs (an cua so console).
cd /d "%~dp0"
where py >nul 2>nul && (py -3 src\app.py --open %*) || (python src\app.py --open %*)
if errorlevel 1 pause
