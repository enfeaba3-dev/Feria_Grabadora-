@echo off
setlocal
cd /d "%~dp0"
title Feria Transcriber 2.0 - Tests
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta instalar.bat antes de los tests.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m unittest discover -s tests -v > "logs\tests.log" 2>&1
set CODE=%errorlevel%
type "logs\tests.log"
echo.
pause
exit /b %CODE%
